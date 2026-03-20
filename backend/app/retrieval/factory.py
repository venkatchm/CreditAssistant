from __future__ import annotations

from pathlib import Path

from app.core.settings import Settings
from app.retrieval.persistence import RetrievalPersistenceBackend
from app.retrieval.postgres_store import PostgresRetrievalPersistence
from app.retrieval.sqlite_store import RetrievalDatabase, RetrievalPersistence


def build_retrieval_persistence(settings: Settings, base_dir: Path) -> RetrievalPersistenceBackend:
    if settings.retrieval_backend == "postgres":
        if not settings.retrieval_postgres_dsn:
            raise RuntimeError("RETRIEVAL_POSTGRES_DSN is required when RETRIEVAL_BACKEND=postgres.")
        migration_sql = (base_dir / "migrations" / "0002_retrieval_schema_postgres.sql").read_text(encoding="utf-8")
        return PostgresRetrievalPersistence(
            dsn=settings.retrieval_postgres_dsn,
            embedding_model=settings.retrieval_embedding_model,
            migration_sql=migration_sql,
        )

    database = RetrievalDatabase(
        db_path=settings.retrieval_db_path,
        migration_path=base_dir / "migrations" / "0001_retrieval_schema.sql",
    )
    return RetrievalPersistence(
        database=database,
        embedding_model=settings.retrieval_embedding_model,
    )
