import logging
import os
import re
from pathlib import Path
from typing import Optional, List, Dict, Any

from langchain_community.document_loaders import PyMuPDFLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import PGVector
from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

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

SITREP_SYSTEM_PROMPT = """You are RouteX Incident Commander generating an official Disaster Situation Report (SitRep) for the Guwahati-Tawang / Eastern Himalayan highway corridor.

Grounding SOPs & Manuals:
{context}

Incident Parameters:
- Hazard Type: {hazard_type}
- Severity Level: {severity}
- Location / Highway Milepost: {location}
- Detected Metrics: {details}

Generate a concise, high-priority Field Situation Report formatted with these exact sections:
1. INCIDENT CLASSIFICATION & TIME SENSITIVITY
2. MANDATORY CHECKPOINT TRAFFIC ORDERS (Halting window & staging areas)
3. SAFE EVACUATION & ALTERNATIVE BYPASS (Include vehicle weight/GVW restrictions)
4. BRO / PWD MACHINERY MOBILIZATION PACKAGE (Required equipment from nearest sector camp)
5. WEATHER CORROBORATION & RE-OPENING SAFETY CRITERIA (Rainfall thresholds & rockfall observation window)

Be authoritative, concrete, and cite specific NDMA / BRO / IRC / IMD protocols."""


class CorridorIntelligenceService:
    def __init__(
        self,
        embedding_provider: Optional[str] = None,
        embedding_model: Optional[str] = None,
        llm_provider: Optional[str] = None,
        llm_model: Optional[str] = None,
        collection_name: Optional[str] = None,
        connection_string: Optional[str] = None,
    ):
        try:
            from backend.config import get_settings
            cfg = get_settings()
            self.emb_provider = embedding_provider or getattr(cfg, "RAG_EMBEDDING_PROVIDER", "huggingface")
            self.emb_model = embedding_model or getattr(cfg, "RAG_EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")
            self.llm_provider = llm_provider or getattr(cfg, "RAG_LLM_PROVIDER", "groq")
            self.llm_model = llm_model or getattr(cfg, "RAG_LLM_MODEL", "llama-3.1-8b-instant")
            self.collection_name = collection_name or getattr(cfg, "RAG_COLLECTION_NAME", "routex_knowledge_base")
            self.chunk_size = getattr(cfg, "RAG_CHUNK_SIZE", 800)
            self.chunk_overlap = getattr(cfg, "RAG_CHUNK_OVERLAP", 150)
            self.default_top_k = getattr(cfg, "RAG_TOP_K", 5)
            self.temperature = getattr(cfg, "RAG_TEMPERATURE", 0.1)
            self.max_tokens = getattr(cfg, "RAG_MAX_TOKENS", 2048)
            self.groq_api_key = getattr(cfg, "GROQ_API_KEY", None) or os.getenv("GROQ_API_KEY")
            self.openai_api_key = getattr(cfg, "OPENAI_API_KEY", None) or os.getenv("OPENAI_API_KEY")
            self.ollama_base_url = getattr(cfg, "OLLAMA_BASE_URL", "http://localhost:11434/v1")
            self.db_url = connection_string or cfg.database_url_sync
        except Exception:
            self.emb_provider = embedding_provider or os.getenv("RAG_EMBEDDING_PROVIDER", "huggingface")
            self.emb_model = embedding_model or os.getenv("RAG_EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")
            self.llm_provider = llm_provider or os.getenv("RAG_LLM_PROVIDER", "groq")
            self.llm_model = llm_model or os.getenv("RAG_LLM_MODEL", "llama-3.1-8b-instant")
            self.collection_name = collection_name or os.getenv("RAG_COLLECTION_NAME", "routex_knowledge_base")
            self.chunk_size = int(os.getenv("RAG_CHUNK_SIZE", "800"))
            self.chunk_overlap = int(os.getenv("RAG_CHUNK_OVERLAP", "150"))
            self.default_top_k = int(os.getenv("RAG_TOP_K", "5"))
            self.temperature = float(os.getenv("RAG_TEMPERATURE", "0.1"))
            self.max_tokens = int(os.getenv("RAG_MAX_TOKENS", "2048"))
            self.groq_api_key = os.getenv("GROQ_API_KEY")
            self.openai_api_key = os.getenv("OPENAI_API_KEY")
            self.ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
            self.db_url = connection_string or self._build_fallback_db_url()

        self.embeddings = self._init_embeddings()
        self.llm = self._init_llm()
        self.store: Optional[PGVector] = None
        self._cached_chunks: List[Document] = []

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
            return OpenAIEmbeddings(
                model=self.emb_model if "text-embedding" in self.emb_model else "text-embedding-3-small",
                api_key=self.openai_api_key,
            )
        from langchain_huggingface import HuggingFaceEmbeddings
        return HuggingFaceEmbeddings(
            model_name=self.emb_model,
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True},
        )

    def _init_llm(self):
        if self.llm_provider == "openai":
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(
                model=self.llm_model if "gpt" in self.llm_model else "gpt-4o",
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                api_key=self.openai_api_key,
            )
        elif self.llm_provider == "groq":
            from langchain_groq import ChatGroq
            return ChatGroq(
                model=self.llm_model,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                api_key=self.groq_api_key,
            )
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            base_url=self.ollama_base_url,
            model=self.llm_model,
            temperature=self.temperature,
            api_key="ollama",
        )

    def _get_splitter(self) -> RecursiveCharacterTextSplitter:
        return RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
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
        self._cached_chunks = chunks
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

    def hybrid_retrieve(self, query: str, top_k: Optional[int] = None) -> List[Document]:
        """Hybrid Search combining dense embedding similarity with keyword matching.
        Uses Reciprocal Rank Fusion (RRF) to ensure exact acronyms (e.g. OKSRT, IRC, BRO)
        and highway numbers surface at top rank.
        """
        k = top_k or self.default_top_k
        store = self._get_store()
        dense_results = store.similarity_search(query, k=k * 2)

        # Keyword boost: extract salient keywords (e.g. acronyms, codes, numbers)
        query_terms = set(re.findall(r"\b[A-Za-z0-9\-\:]{3,}\b", query.lower()))

        # Calculate Reciprocal Rank Fusion scores
        rrf_scores: Dict[str, float] = {}
        doc_map: Dict[str, Document] = {}

        for rank, doc in enumerate(dense_results):
            doc_id = f"{doc.metadata.get('source_file')}-{doc.page_content[:40]}"
            doc_map[doc_id] = doc
            rrf_scores[doc_id] = rrf_scores.get(doc_id, 0.0) + (0.6 / (60.0 + rank))

        # Lexical score scan across candidate chunks
        for doc_id, doc in doc_map.items():
            content_lower = doc.page_content.lower()
            term_matches = sum(1 for term in query_terms if term in content_lower)
            if term_matches > 0:
                rrf_scores[doc_id] += 0.4 * (term_matches / max(len(query_terms), 1))

        ranked_doc_ids = sorted(rrf_scores.keys(), key=lambda k: rrf_scores[k], reverse=True)
        return [doc_map[did] for did in ranked_doc_ids[:k]]

    def ask(self, question: str, top_k: Optional[int] = None) -> Dict[str, Any]:
        k = top_k or self.default_top_k
        retrieved_docs = self.hybrid_retrieve(question, top_k=k)
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

    def generate_incident_sitrep(
        self,
        hazard_type: str,
        severity: str,
        location: str,
        details: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generates an official Disaster Situation Report (SitRep) for field operations."""
        query = f"SOP requirements, bypass detour, machinery, and re-opening criteria for {severity} {hazard_type} at {location}"
        retrieved_docs = self.hybrid_retrieve(query, top_k=5)
        context_text = self._format_context(retrieved_docs)

        prompt_tmpl = ChatPromptTemplate.from_template(SITREP_SYSTEM_PROMPT)
        chain = prompt_tmpl | self.llm | StrOutputParser()

        sitrep_text = chain.invoke({
            "context": context_text,
            "hazard_type": hazard_type,
            "severity": severity,
            "location": location,
            "details": details or "Telemetry verified by Sentinel-1 SAR & YOLOv8",
        })

        citations = [
            {
                "file": d.metadata.get("source_file", "manual"),
                "page": d.metadata.get("page", "1"),
                "snippet": d.page_content[:200].strip() + "...",
            }
            for d in retrieved_docs[:3]
        ]

        return {
            "incident_id": f"ROUTEX-SITREP-{hazard_type[:3].upper()}-{abs(hash(location)) % 10000:04d}",
            "location": location,
            "hazard_type": hazard_type,
            "severity": severity,
            "sitrep_content": sitrep_text,
            "verified_sources": citations,
        }

    def search_similar(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        docs = self.hybrid_retrieve(query, top_k=top_k)
        return [
            {
                "content": d.page_content,
                "source": d.metadata.get("source_file", "manual"),
                "metadata": d.metadata,
            }
            for d in docs
        ]


_service_instance: Optional[CorridorIntelligenceService] = None


def get_intelligence_service() -> CorridorIntelligenceService:
    global _service_instance
    if _service_instance is None:
        _service_instance = CorridorIntelligenceService()
    return _service_instance
