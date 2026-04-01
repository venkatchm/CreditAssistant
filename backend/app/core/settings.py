from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    app_env: str
    retrieval_backend: str
    retrieval_db_path: Path
    retrieval_postgres_dsn: str | None
    retrieval_embedding_model: str
    model_backend: str
    openai_api_key: str | None
    openai_model: str | None
    openai_base_url: str | None
    model_base_url: str | None
    model_api_key: str | None
    model_name: str | None
    anthropic_api_key: str | None
    anthropic_model: str | None
    embedding_provider: str
    embedding_dimensions: int
    embedding_batch_size: int
    ingestion_chunk_max_chars: int
    ingestion_chunk_overlap: int
    credit_data_backend: str


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    base_dir = Path(__file__).resolve().parents[2]
    return Settings(
        app_env=os.getenv("APP_ENV", "local"),
        retrieval_backend=os.getenv("RETRIEVAL_BACKEND", "sqlite").lower(),
        retrieval_db_path=Path(os.getenv("RETRIEVAL_DB_PATH", str(base_dir / "data" / "retrieval.sqlite3"))),
        retrieval_postgres_dsn=os.getenv("RETRIEVAL_POSTGRES_DSN"),
        retrieval_embedding_model=os.getenv("RETRIEVAL_EMBEDDING_MODEL", "LocalHashEmbeddingProvider"),
        model_backend=os.getenv("MODEL_BACKEND", "local").lower(),
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-5"),
        openai_base_url=os.getenv("OPENAI_BASE_URL"),
        model_base_url=os.getenv("MODEL_BASE_URL"),
        model_api_key=os.getenv("MODEL_API_KEY"),
        model_name=os.getenv("MODEL_NAME"),
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
        anthropic_model=os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001"),
        embedding_provider=os.getenv("EMBEDDING_PROVIDER", "hash"),
        embedding_dimensions=int(os.getenv("EMBEDDING_DIMENSIONS", "1536")),
        embedding_batch_size=int(os.getenv("EMBEDDING_BATCH_SIZE", "100")),
        ingestion_chunk_max_chars=int(os.getenv("INGESTION_CHUNK_MAX_CHARS", "800")),
        ingestion_chunk_overlap=int(os.getenv("INGESTION_CHUNK_OVERLAP", "1")),
        credit_data_backend=os.getenv("CREDIT_DATA_BACKEND", "json").lower(),
    )
