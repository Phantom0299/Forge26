import pytest
from pathlib import Path
from backend.services.rag import CorridorIntelligenceService, TACTICAL_DISPATCH_PROMPT


def test_corridor_intelligence_init():
    service = CorridorIntelligenceService(
        embedding_provider="huggingface",
        llm_provider="groq",
        collection_name="test_collection",
        connection_string="postgresql+psycopg://test:test@localhost:5432/test",
    )
    assert service.collection_name == "test_collection"
    assert service.emb_provider == "huggingface"
    assert service.llm_provider == "groq"


def test_format_context():
    from langchain_core.documents import Document

    service = CorridorIntelligenceService()
    docs = [
        Document(page_content="Class 3 landslide protocol: Halt traffic within 15 mins.", metadata={"source_file": "ndma_landslide_sop.md", "page": "2"}),
        Document(page_content="OKSRT bypass GVW limit: 16.2 tonnes.", metadata={"source_file": "ndma_landslide_sop.md", "page": "3"}),
    ]
    formatted = service._format_context(docs)
    assert "[Ref 1 | ndma_landslide_sop.md (Page 2)]" in formatted
    assert "[Ref 2 | ndma_landslide_sop.md (Page 3)]" in formatted
    assert "16.2 tonnes" in formatted


def test_rag_documents_exist():
    rag_dir = Path("data/rag_documents")
    assert rag_dir.exists(), "data/rag_documents should exist"
    
    expected_manuals = [
        "ndma_landslide_sop.md",
        "irc_sp_48_hill_roads.md",
        "bro_mountain_road_clearance.md",
        "imd_weather_alert_protocols.md",
    ]
    for manual in expected_manuals:
        manual_path = rag_dir / manual
        assert manual_path.exists(), f"Expected manual {manual} not found"
        assert manual_path.stat().st_size > 500, f"Manual {manual} should have substantive content"
