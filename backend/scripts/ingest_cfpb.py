"""Fetch CFPB credit education content, chunk, embed, and store.

Usage:
    PYTHONPATH=backend python3 backend/scripts/ingest_cfpb.py

Set EMBEDDING_PROVIDER=openai and OPENAI_API_KEY for production embeddings.
Set RETRIEVAL_BACKEND=postgres and RETRIEVAL_POSTGRES_DSN for pgvector storage.
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

# Ensure backend is on sys.path
backend_dir = Path(__file__).resolve().parents[1]
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.core.settings import get_settings
from app.retrieval.cfpb_client import CfpbClient
from app.retrieval.chunking import SentenceChunker
from app.retrieval.embeddings import LocalHashEmbeddingProvider, OpenAIEmbeddingProvider
from app.retrieval.factory import build_retrieval_persistence
from app.retrieval.ingestion import IngestionPipeline
from app.retrieval.models import SourceDocument

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def load_local_knowledge(knowledge_path: Path) -> list[SourceDocument]:
    """Load any custom knowledge from the local knowledge.json file."""
    if not knowledge_path.exists():
        logger.info("No local knowledge.json found at %s, skipping", knowledge_path)
        return []
    with knowledge_path.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    docs = [SourceDocument(**row) for row in payload]
    logger.info("Loaded %d local knowledge documents", len(docs))
    return docs


def main() -> None:
    settings = get_settings()
    base_dir = Path(__file__).resolve().parents[1]

    # Build embedding provider
    if settings.embedding_provider == "openai":
        if not settings.openai_api_key:
            logger.error("OPENAI_API_KEY is required when EMBEDDING_PROVIDER=openai")
            sys.exit(1)
        embedding_provider = OpenAIEmbeddingProvider(
            api_key=settings.openai_api_key,
            dimensions=settings.embedding_dimensions,
            batch_size=settings.embedding_batch_size,
        )
        logger.info("Using OpenAI embeddings (model=text-embedding-3-small, dims=%d)", settings.embedding_dimensions)
    else:
        embedding_provider = LocalHashEmbeddingProvider()
        logger.info("Using local hash embeddings (dev mode)")

    # Build persistence backend
    persistence = build_retrieval_persistence(settings=settings, base_dir=base_dir)
    logger.info("Using %s retrieval backend", settings.retrieval_backend)

    # Build chunker with production settings
    chunker = SentenceChunker(
        max_chars=settings.ingestion_chunk_max_chars,
        overlap_sentences=settings.ingestion_chunk_overlap,
    )

    # Fetch CFPB content
    cache_dir = base_dir / "data" / "cfpb_cache"
    logger.info("Fetching CFPB content (cache_dir=%s)...", cache_dir)

    with CfpbClient(cache_dir=cache_dir) as client:
        cfpb_docs = client.fetch_all()

    # Also load local knowledge
    local_docs = load_local_knowledge(base_dir / "data" / "knowledge.json")

    all_docs = local_docs + cfpb_docs
    logger.info("Total documents to ingest: %d (%d local + %d CFPB)", len(all_docs), len(local_docs), len(cfpb_docs))

    if not all_docs:
        logger.warning("No documents to ingest. Check CFPB API connectivity.")
        sys.exit(1)

    # Run ingestion pipeline
    pipeline = IngestionPipeline(
        chunker=chunker,
        embedding_provider=embedding_provider,
        persistence=persistence,
    )
    chunks = pipeline.ingest(all_docs)

    logger.info("Ingestion complete: %d documents -> %d chunks", len(all_docs), len(chunks))

    # Print summary by source
    sources: dict[str, int] = {}
    for doc in all_docs:
        sources[doc.source] = sources.get(doc.source, 0) + 1
    for source, count in sorted(sources.items()):
        logger.info("  %s: %d documents", source, count)


if __name__ == "__main__":
    main()
