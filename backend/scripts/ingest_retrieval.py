from __future__ import annotations

import sys
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.append(str(BASE_DIR))

from app.retrieval.chunking import SentenceChunker
from app.retrieval.embeddings import LocalHashEmbeddingProvider
from app.retrieval.ingestion import JsonKnowledgeIngestionPipeline
from app.retrieval.sqlite_store import RetrievalDatabase, RetrievalPersistence


def main() -> None:
    knowledge_path = BASE_DIR / "data" / "knowledge.json"
    db_path = BASE_DIR / "data" / "retrieval.sqlite3"
    migration_path = BASE_DIR / "migrations" / "0001_retrieval_schema.sql"
    embedding_provider = LocalHashEmbeddingProvider()
    database = RetrievalDatabase(db_path=db_path, migration_path=migration_path)
    persistence = RetrievalPersistence(database=database, embedding_model=embedding_provider.__class__.__name__)
    pipeline = JsonKnowledgeIngestionPipeline(
        knowledge_path=knowledge_path,
        chunker=SentenceChunker(),
        embedding_provider=embedding_provider,
        persistence=persistence,
    )
    chunks = pipeline.ingest()
    print(f"Ingested {len(chunks)} retrieval chunks into {db_path}")


if __name__ == "__main__":
    main()
