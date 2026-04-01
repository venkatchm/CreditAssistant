from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel, Field

from app.core.dependencies import get_rag_service
from app.core.settings import get_settings
from app.retrieval.cfpb_client import CfpbClient
from app.retrieval.chunking import SentenceChunker
from app.retrieval.ingestion import IngestionPipeline
from app.retrieval.models import SourceDocument
from app.services.rag_service import RagService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ingestion", tags=["ingestion"])


class IngestionStatus(BaseModel):
    status: str
    message: str
    documents: int = 0
    chunks: int = 0


class IngestDocumentsRequest(BaseModel):
    documents: list[SourceDocument] = Field(..., description="List of documents to ingest")


# Simple in-memory status tracker for background jobs
_job_status: dict[str, IngestionStatus] = {}


@router.post("/cfpb", response_model=IngestionStatus)
def ingest_cfpb(background_tasks: BackgroundTasks, rag_service: RagService = Depends(get_rag_service)):
    """Trigger CFPB content ingestion as a background task."""
    _job_status["cfpb"] = IngestionStatus(status="running", message="CFPB ingestion started")
    background_tasks.add_task(_run_cfpb_ingestion, rag_service)
    return _job_status["cfpb"]


@router.post("/documents", response_model=IngestionStatus)
def ingest_documents(request: IngestDocumentsRequest, rag_service: RagService = Depends(get_rag_service)):
    """Ingest custom documents directly via API."""
    settings = get_settings()
    chunker = SentenceChunker(
        max_chars=settings.ingestion_chunk_max_chars,
        overlap_sentences=settings.ingestion_chunk_overlap,
    )
    pipeline = IngestionPipeline(
        chunker=chunker,
        embedding_provider=rag_service.embedding_provider,
        persistence=rag_service.persistence,
    )
    chunks = pipeline.ingest(request.documents)
    return IngestionStatus(
        status="completed",
        message=f"Ingested {len(request.documents)} documents into {len(chunks)} chunks",
        documents=len(request.documents),
        chunks=len(chunks),
    )


@router.get("/status", response_model=IngestionStatus)
def ingestion_status():
    """Check the status of the last CFPB ingestion job."""
    return _job_status.get("cfpb", IngestionStatus(status="idle", message="No ingestion job has been run"))


@router.post("/rebuild", response_model=IngestionStatus)
def rebuild_index(rag_service: RagService = Depends(get_rag_service)):
    """Rebuild the index from local knowledge.json only."""
    rag_service.rebuild_index()
    return IngestionStatus(status="completed", message="Index rebuilt from local knowledge.json")


def _run_cfpb_ingestion(rag_service: RagService) -> None:
    """Background task that fetches CFPB content and ingests it."""
    try:
        settings = get_settings()
        base_dir = Path(__file__).resolve().parents[3]
        cache_dir = base_dir / "data" / "cfpb_cache"

        logger.info("Starting CFPB ingestion...")

        with CfpbClient(cache_dir=cache_dir) as client:
            cfpb_docs = client.fetch_all()

        # Load local knowledge too
        knowledge_path = base_dir / "data" / "knowledge.json"
        local_docs: list[SourceDocument] = []
        if knowledge_path.exists():
            import json
            with knowledge_path.open("r", encoding="utf-8") as f:
                local_docs = [SourceDocument(**row) for row in json.load(f)]

        all_docs = local_docs + cfpb_docs
        logger.info("Total documents to ingest: %d", len(all_docs))

        chunker = SentenceChunker(
            max_chars=settings.ingestion_chunk_max_chars,
            overlap_sentences=settings.ingestion_chunk_overlap,
        )
        pipeline = IngestionPipeline(
            chunker=chunker,
            embedding_provider=rag_service.embedding_provider,
            persistence=rag_service.persistence,
        )
        chunks = pipeline.ingest(all_docs)

        _job_status["cfpb"] = IngestionStatus(
            status="completed",
            message=f"Ingested {len(all_docs)} documents into {len(chunks)} chunks",
            documents=len(all_docs),
            chunks=len(chunks),
        )
        logger.info("CFPB ingestion complete: %d docs, %d chunks", len(all_docs), len(chunks))

    except Exception as exc:
        logger.exception("CFPB ingestion failed")
        _job_status["cfpb"] = IngestionStatus(status="failed", message=str(exc))
