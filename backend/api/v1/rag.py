import logging
from pathlib import Path
import tempfile
import shutil
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel, Field

from backend.services.rag import get_intelligence_service

logger = logging.getLogger("routex.api.intelligence")

router = APIRouter(prefix="/rag", tags=["Corridor Intelligence & SOP Assistant"])


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=2000, description="Field question or protocol check")
    top_k: int = Field(default=5, ge=1, le=15)


class Citation(BaseModel):
    file: str
    page: str | int
    snippet: str


class QueryResponse(BaseModel):
    question: str
    answer: str
    sources: List[Citation]
    chunks_retrieved: int


class VisionIncidentPayload(BaseModel):
    hazard_type: str = Field(..., example="landslide", description="Detected hazard: landslide, flood, road_damage, rockfall")
    severity: str = Field(..., example="Class 3", description="Class 1 to 4 or Low/Medium/High")
    location: str = Field(..., example="Bhalukpong-Bomdila Km 42 (Guwahati-Tawang)", description="Corridor segment identifier")
    water_depth_m: Optional[float] = Field(default=None, description="SAR-derived surface water depth in meters")
    blockage_pct: Optional[float] = Field(default=None, description="YOLO/U-Net estimated carriageway obstruction percentage")


class VisionActionResponse(BaseModel):
    incident: Dict[str, Any]
    dispatch_guidance: str
    grounding_sources: List[Citation]


class IngestSummary(BaseModel):
    message: str
    chunks_indexed: int
    source: str


@router.post("/query", response_model=QueryResponse)
async def query_assistant(payload: QueryRequest):
    """Answers operator queries grounded against NDMA, BRO, IRC, and IMD mountain manuals."""
    try:
        service = get_intelligence_service()
        result = service.ask(payload.question, top_k=payload.top_k)
        return QueryResponse(**result)
    except Exception as exc:
        logger.error(f"Failed query processing: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/vision-action", response_model=VisionActionResponse)
async def auto_resolve_vision_incident(payload: VisionIncidentPayload):
    """Closed-loop Vision-to-SOP Dispatcher:
    Receives hazard detection output from Sentinel-1 SAR or YOLO/U-Net vision models
    and automatically retrieves the corresponding evacuation detour, machinery checklist,
    and road re-opening criteria.
    """
    try:
        service = get_intelligence_service()
        result = service.resolve_vision_incident(
            hazard_type=payload.hazard_type,
            severity=payload.severity,
            location=payload.location,
            water_depth_m=payload.water_depth_m,
            blockage_pct=payload.blockage_pct,
        )
        return VisionActionResponse(**result)
    except Exception as exc:
        logger.error(f"Vision incident dispatch failed: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/search")
async def semantic_search(query: str, limit: int = 5):
    """Raw similarity search across the vector collection without LLM synthesis."""
    try:
        service = get_intelligence_service()
        return service.search_similar(query, top_k=limit)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/ingest", response_model=IngestSummary)
async def upload_and_ingest(file: UploadFile = File(...)):
    """Upload a new SOP manual (PDF or Markdown) into pgvector."""
    allowed = {".pdf", ".md", ".txt"}
    ext = Path(file.filename).suffix.lower() if file.filename else ""
    if ext not in allowed:
        raise HTTPException(status_code=400, detail=f"Unsupported format '{ext}'. Must be {allowed}")

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
            shutil.copyfileobj(file.file, tmp)
            tmp_path = Path(tmp.name)

        service = get_intelligence_service()
        chunks = service.ingest(str(tmp_path), reset_collection=False)
        tmp_path.unlink(missing_ok=True)

        return IngestSummary(
            message=f"Indexed '{file.filename}' into pgvector",
            chunks_indexed=chunks,
            source=file.filename or "uploaded_manual",
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
