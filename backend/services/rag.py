import logging
import os
from pathlib import Path
from typing import Optional, List, Dict, Any

from langchain_community.document_loaders import PyMuPDFLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import PGVector
from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough

logger = logging.getLogger("routex.intelligence")

TACTICAL_DISPATCH_PROMPT = """You are RouteX Tactical Dispatch, assisting hill corridor response units and logistics planners in the Eastern Himalayas (Guwahati-Tawang and Sikkim corridors).

Reference Knowledge Base:
{context}

Situation / Query:
{question}

Instructions:
- Provide direct, actionable operational guidance tailored to mountain road conditions.
- Cite the exact source manuals (NDMA, BRO, IRC, IMD) for each protocol or specification.
- Include concrete metrics (hazard classifications, machinery rosters, rainfall thresholds, bypass vehicle weight limits) from the documents.
- State clearly if a specific detail is not found in the knowledge base."""


class CorridorIntelligenceService:
    def __init__(
        self,
        embedding_provider: Optional[str] = None,
        llm_provider: Optional[str] = None,
        collection_name: Optional[str] = None,
        connection_string: Optional[str] = None,
    ):
        try:
            from backend.config import get_settings
            cfg = get_settings()
            self.emb_provider = embedding_provider or getattr(cfg, "RAG_EMBEDDING_PROVIDER", "huggingface")
            self.llm_provider = llm_provider or getattr(cfg, "RAG_LLM_PROVIDER", "groq")
            self.collection_name = collection_name or getattr(cfg, "RAG_COLLECTION_NAME", "routex_knowledge_base")
            self.db_url = connection_string or cfg.database_url_sync
        except Exception:
            self.emb_provider = embedding_provider or "huggingface"
            self.llm_provider = llm_provider or "groq"
            self.collection_name = collection_name or "routex_knowledge_base"
            self.db_url = connection_string or self._build_fallback_db_url()

        self.embeddings = self._init_embeddings()
        self.llm = self._init_llm()
        self.store: Optional[PGVector] = None
        self.chain = None

    def _build_fallback_db_url(self) -> str:
        user = os.getenv("POSTGRES_USER", "nerlink_user")
        pwd = os.getenv("POSTGRES_PASSWORD", "nerlink_secure_password")
        host = os.getenv("POSTGRES_HOST", "localhost")
        port = os.getenv("POSTGRES_PORT", "55432")
        db = os.getenv("POSTGRES_DB", "nerlink")
        return f"postgresql+psycopg://{user}:{pwd}@{host}:{port}/{db}"

    def _init_embeddings(self):
        if self.emb_provider == "openai":
            from langchain_openai import OpenAIEmbeddings
            return OpenAIEmbeddings(model="text-embedding-3-small")
        from langchain_huggingface import HuggingFaceEmbeddings
        return HuggingFaceEmbeddings(
            model_name="BAAI/bge-small-en-v1.5",
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True},
        )

    def _init_llm(self):
        if self.llm_provider == "openai":
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(model="gpt-4o", temperature=0.1, max_tokens=2048)
        elif self.llm_provider == "groq":
            from langchain_groq import ChatGroq
            return ChatGroq(model="llama-3.1-8b-instant", temperature=0.1, max_tokens=2048)
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            base_url="http://localhost:11434/v1",
            model="llama3",
            temperature=0.1,
            api_key="ollama",
        )

    def _get_splitter(self) -> RecursiveCharacterTextSplitter:
        return RecursiveCharacterTextSplitter(
            chunk_size=800,
            chunk_overlap=150,
            length_function=len,
            separators=["\n\n", "\n", ". ", ", ", " ", ""],
        )

    def _load_documents(self, target_path: Path) -> List[Document]:
        loaded_docs: List[Document] = []
        target_files = [target_path] if target_path.is_file() else sorted(target_path.rglob("*"))

        for file_path in target_files:
            if not file_path.is_file():
                continue
            ext = file_path.suffix.lower()
            try:
                if ext == ".pdf":
                    loader = PyMuPDFLoader(str(file_path))
                elif ext in (".md", ".txt"):
                    loader = TextLoader(str(file_path), encoding="utf-8")
                else:
                    continue

                items = loader.load()
                for item in items:
                    item.metadata["source_file"] = file_path.name
                    item.metadata["source_path"] = str(file_path)
                loaded_docs.extend(items)
            except Exception as err:
                logger.warning(f"Skipping {file_path.name}: {err}")

        return loaded_docs

    def ingest(self, source_path: str, reset_collection: bool = False) -> int:
        path = Path(source_path)
        if not path.exists():
            raise FileNotFoundError(f"Source not found: {source_path}")

        raw_docs = self._load_documents(path)
        if not raw_docs:
            logger.warning("No parseable documents found.")
            return 0

        chunks = self._get_splitter().split_documents(raw_docs)
        logger.info(f"Loaded {len(raw_docs)} pages -> {len(chunks)} text chunks.")

        if reset_collection or self.store is None:
            self.store = PGVector.from_documents(
                documents=chunks,
                embedding=self.embeddings,
                connection=self.db_url,
                collection_name=self.collection_name,
                pre_delete_collection=reset_collection,
            )
        else:
            self.store.add_documents(chunks)

        return len(chunks)

    def _get_store(self) -> PGVector:
        if self.store is None:
            self.store = PGVector(
                embedding_function=self.embeddings,
                connection=self.db_url,
                collection_name=self.collection_name,
            )
        return self.store

    def _format_context(self, docs: List[Document]) -> str:
        parts = []
        for idx, doc in enumerate(docs, 1):
            src = doc.metadata.get("source_file", "manual")
            pg = doc.metadata.get("page", "1")
            parts.append(f"[Ref {idx} | {src} (Page {pg})]\n{doc.page_content}")
        return "\n\n---\n\n".join(parts)

    def ask(self, question: str, top_k: int = 5) -> Dict[str, Any]:
        store = self._get_store()
        retrieved_docs = store.similarity_search(question, k=top_k)

        context_text = self._format_context(retrieved_docs)
        prompt_tmpl = ChatPromptTemplate.from_template(TACTICAL_DISPATCH_PROMPT)
        chain = prompt_tmpl | self.llm | StrOutputParser()

        answer = chain.invoke({"context": context_text, "question": question})

        citations = []
        for d in retrieved_docs:
            citations.append({
                "file": d.metadata.get("source_file", "manual"),
                "page": d.metadata.get("page", "1"),
                "snippet": d.page_content[:240].strip() + ("..." if len(d.page_content) > 240 else ""),
            })

        return {
            "question": question,
            "answer": answer,
            "sources": citations,
            "chunks_retrieved": len(retrieved_docs),
        }

    def resolve_vision_incident(
        self,
        hazard_type: str,
        severity: str,
        location: str,
        water_depth_m: Optional[float] = None,
        blockage_pct: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Bridges Vision model detections directly into actionable RAG SOP retrieval."""
        hazard_query = (
            f"Emergency response clearance protocol and evacuation diversion for "
            f"{severity} {hazard_type} near {location}."
        )
        if water_depth_m is not None:
            hazard_query += f" Water depth measured at {water_depth_m:.2f} meters."
        if blockage_pct is not None:
            hazard_query += f" Roadway blockage estimated at {blockage_pct:.0f}%."

        result = self.ask(hazard_query, top_k=4)

        return {
            "incident": {
                "hazard_type": hazard_type,
                "severity": severity,
                "location": location,
                "water_depth_m": water_depth_m,
                "blockage_pct": blockage_pct,
            },
            "dispatch_guidance": result["answer"],
            "grounding_sources": result["sources"],
        }

    def search_similar(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        store = self._get_store()
        matches = store.similarity_search_with_score(query, k=top_k)
        return [
            {
                "content": item.page_content,
                "score": float(score),
                "source": item.metadata.get("source_file", "unknown"),
                "metadata": item.metadata,
            }
            for item, score in matches
        ]


_service_instance: Optional[CorridorIntelligenceService] = None


def get_intelligence_service() -> CorridorIntelligenceService:
    global _service_instance
    if _service_instance is None:
        _service_instance = CorridorIntelligenceService()
    return _service_instance
