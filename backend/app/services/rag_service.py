from __future__ import annotations

from pathlib import Path
from threading import Lock

from app.core.settings import Settings, get_settings
from app.retrieval.chunking import SentenceChunker
from app.retrieval.embeddings import EmbeddingProvider, LocalHashEmbeddingProvider, OpenAIEmbeddingProvider
from app.retrieval.factory import build_retrieval_persistence
from app.retrieval.ingestion import JsonKnowledgeIngestionPipeline
from app.retrieval.persistent_hybrid import PersistentHybridRetriever
from app.schemas.chat import RetrievalDocument, RetrievalResult


class RagService:
    def __init__(
        self,
        knowledge_path: Path | None = None,
        db_path: Path | None = None,
        embedding_provider: EmbeddingProvider | None = None,
        min_score: float = 0.005,
    ) -> None:
        base_dir = Path(__file__).resolve().parents[2]
        settings = self._resolve_settings(db_path=db_path, defaults=get_settings())
        self.knowledge_path = knowledge_path or base_dir / "data" / "knowledge.json"
        self.db_path = db_path or settings.retrieval_db_path
        self.embedding_provider = embedding_provider or self._build_embedding_provider(settings)
        self.min_score = min_score
        self.persistence = build_retrieval_persistence(settings=settings, base_dir=base_dir)
        self._index_lock = Lock()
        self._pipeline = JsonKnowledgeIngestionPipeline(
            knowledge_path=self.knowledge_path,
            chunker=SentenceChunker(),
            embedding_provider=self.embedding_provider,
            persistence=self.persistence,
        )
        if not self._has_indexed_chunks():
            with self._index_lock:
                if not self._has_indexed_chunks():
                    # Build the index once during warmup instead of letting concurrent requests repeat it.
                    self._pipeline.ingest()
        self._retriever = PersistentHybridRetriever(
            embedding_provider=self.embedding_provider,
            persistence=self.persistence,
        )

    def search_knowledge(self, query: str) -> RetrievalResult:
        retrieved_chunks = self._retriever.search(query, top_k=3)
        documents = [
            RetrievalDocument(
                doc_id=chunk.doc_id,
                topic=chunk.topic,
                title=chunk.title,
                snippet=chunk.content,
                source=chunk.source,
                confidence=min(chunk.score, 1.0),
                effective_date=chunk.effective_date,
                version=chunk.version,
            )
            for chunk in retrieved_chunks
            if chunk.score >= self.min_score
        ]
        return RetrievalResult(
            query=query,
            documents=documents,
            used=bool(documents),
            top_confidence=documents[0].confidence if documents else 0.0,
        )

    def rebuild_index(self) -> None:
        self._pipeline.ingest()

    def _has_indexed_chunks(self) -> bool:
        return self.persistence.has_indexed_chunks()

    @staticmethod
    def _build_embedding_provider(settings: Settings) -> EmbeddingProvider:
        if settings.embedding_provider == "openai":
            if not settings.openai_api_key:
                raise RuntimeError("OPENAI_API_KEY is required when EMBEDDING_PROVIDER=openai")
            return OpenAIEmbeddingProvider(
                api_key=settings.openai_api_key,
                dimensions=settings.embedding_dimensions,
                batch_size=settings.embedding_batch_size,
            )
        return LocalHashEmbeddingProvider()

    def _resolve_settings(self, db_path: Path | None, defaults: Settings) -> Settings:
        if db_path is None:
            return defaults
        return Settings(
            app_env=defaults.app_env,
            retrieval_backend="sqlite",
            retrieval_db_path=db_path,
            retrieval_postgres_dsn=defaults.retrieval_postgres_dsn,
            retrieval_embedding_model=defaults.retrieval_embedding_model,
            model_backend=defaults.model_backend,
            openai_api_key=defaults.openai_api_key,
            openai_model=defaults.openai_model,
            openai_base_url=defaults.openai_base_url,
            model_base_url=defaults.model_base_url,
            model_api_key=defaults.model_api_key,
            model_name=defaults.model_name,
            anthropic_api_key=defaults.anthropic_api_key,
            anthropic_model=defaults.anthropic_model,
            embedding_provider=defaults.embedding_provider,
            embedding_dimensions=defaults.embedding_dimensions,
            embedding_batch_size=defaults.embedding_batch_size,
            ingestion_chunk_max_chars=defaults.ingestion_chunk_max_chars,
            ingestion_chunk_overlap=defaults.ingestion_chunk_overlap,
            credit_data_backend=defaults.credit_data_backend,
        )
