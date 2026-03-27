from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.core.settings import Settings
from app.retrieval.factory import build_retrieval_persistence
from app.retrieval.sqlite_store import RetrievalPersistence


class RetrievalBackendFactoryTests(unittest.TestCase):
    def test_sqlite_backend_is_built_by_default_shape(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = Settings(
                app_env="test",
                retrieval_backend="sqlite",
                retrieval_db_path=Path(temp_dir) / "retrieval.sqlite3",
                retrieval_postgres_dsn=None,
                retrieval_embedding_model="LocalHashEmbeddingProvider",
                model_backend="local",
                openai_api_key=None,
                openai_model=None,
                openai_base_url=None,
                model_base_url=None,
                model_api_key=None,
                model_name=None,
                anthropic_api_key=None,
                anthropic_model=None,
                embedding_provider="hash",
                embedding_dimensions=32,
                embedding_batch_size=100,
                ingestion_chunk_max_chars=800,
                ingestion_chunk_overlap=1,
                credit_data_backend="json",
            )
            persistence = build_retrieval_persistence(
                settings=settings,
                base_dir=Path("/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend"),
            )
            self.assertIsInstance(persistence, RetrievalPersistence)

    def test_postgres_backend_requires_dsn(self) -> None:
        settings = Settings(
            app_env="test",
            retrieval_backend="postgres",
            retrieval_db_path=Path("/tmp/retrieval.sqlite3"),
            retrieval_postgres_dsn=None,
            retrieval_embedding_model="LocalHashEmbeddingProvider",
            model_backend="local",
            openai_api_key=None,
            openai_model=None,
            openai_base_url=None,
            model_base_url=None,
            model_api_key=None,
            model_name=None,
            anthropic_api_key=None,
            anthropic_model=None,
            embedding_provider="hash",
            embedding_dimensions=32,
            embedding_batch_size=100,
            ingestion_chunk_max_chars=800,
            ingestion_chunk_overlap=1,
            credit_data_backend="json",
        )
        with self.assertRaises(RuntimeError):
            build_retrieval_persistence(
                settings=settings,
                base_dir=Path("/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend"),
            )


if __name__ == "__main__":
    unittest.main()
