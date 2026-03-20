from __future__ import annotations

from pathlib import Path

from app.retrieval.chunking import SentenceChunker
from app.retrieval.embeddings import EmbeddingProvider, LocalHashEmbeddingProvider
from app.retrieval.ingestion import JsonKnowledgeIngestionPipeline
from app.retrieval.persistent_hybrid import PersistentHybridRetriever
from app.retrieval.sqlite_store import RetrievalDatabase, RetrievalPersistence
from app.schemas.chat import RetrievalDocument, RetrievalResult


class RagService:
    def __init__(
        self,
        knowledge_path: Path | None = None,
        db_path: Path | None = None,
        embedding_provider: EmbeddingProvider | None = None,
        min_score: float = 0.2,
    ) -> None:
        base_dir = Path(__file__).resolve().parents[2]
        self.knowledge_path = knowledge_path or base_dir / "data" / "knowledge.json"
        self.db_path = db_path or base_dir / "data" / "retrieval.sqlite3"
        self.embedding_provider = embedding_provider or LocalHashEmbeddingProvider()
        self.min_score = min_score
        self.database = RetrievalDatabase(
            db_path=self.db_path,
            migration_path=base_dir / "migrations" / "0001_retrieval_schema.sql",
        )
        self.persistence = RetrievalPersistence(
            database=self.database,
            embedding_model=self.embedding_provider.__class__.__name__,
        )
        self._pipeline = JsonKnowledgeIngestionPipeline(
            knowledge_path=self.knowledge_path,
            chunker=SentenceChunker(),
            embedding_provider=self.embedding_provider,
            persistence=self.persistence,
        )
        if not self._has_indexed_chunks():
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
        with self.database.connect() as connection:
            row = connection.execute("SELECT COUNT(*) AS count FROM retrieval_chunks").fetchone()
        return bool(row and row["count"] > 0)
