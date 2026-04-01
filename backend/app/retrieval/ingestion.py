from __future__ import annotations

import json
import logging
from pathlib import Path

from app.retrieval.chunking import SentenceChunker
from app.retrieval.embeddings import EmbeddingProvider
from app.retrieval.models import ChunkedDocument, SourceDocument
from app.retrieval.persistence import RetrievalPersistenceBackend

logger = logging.getLogger(__name__)


class IngestionPipeline:
    """Source-agnostic ingestion pipeline: chunk, embed, store."""

    def __init__(
        self,
        chunker: SentenceChunker,
        embedding_provider: EmbeddingProvider,
        persistence: RetrievalPersistenceBackend,
    ) -> None:
        self.chunker = chunker
        self.embedding_provider = embedding_provider
        self.persistence = persistence

    def ingest(self, documents: list[SourceDocument]) -> list[ChunkedDocument]:
        chunks = [chunk for doc in documents for chunk in self.chunker.chunk(doc)]
        logger.info("Chunked %d documents into %d chunks", len(documents), len(chunks))

        texts = [self._embedding_text(chunk) for chunk in chunks]
        embeddings = self.embedding_provider.embed_batch(texts)
        logger.info("Generated %d embeddings", len(embeddings))

        self.persistence.replace_documents(documents=documents, chunks=chunks, embeddings=embeddings)
        logger.info("Stored %d documents and %d chunks", len(documents), len(chunks))
        return chunks

    @staticmethod
    def _embedding_text(chunk: ChunkedDocument) -> str:
        return " ".join([chunk.title, chunk.topic.replace("_", " "), chunk.content, " ".join(chunk.tags)])


class JsonKnowledgeIngestionPipeline:
    """Backward-compatible pipeline that reads from a JSON file."""

    def __init__(
        self,
        knowledge_path: Path,
        chunker: SentenceChunker,
        embedding_provider: EmbeddingProvider,
        persistence: RetrievalPersistenceBackend,
    ) -> None:
        self.knowledge_path = knowledge_path
        self._pipeline = IngestionPipeline(
            chunker=chunker,
            embedding_provider=embedding_provider,
            persistence=persistence,
        )

    def ingest(self) -> list[ChunkedDocument]:
        documents = self._load_documents()
        return self._pipeline.ingest(documents)

    def _load_documents(self) -> list[SourceDocument]:
        with self.knowledge_path.open("r", encoding="utf-8") as file:
            payload = json.load(file)
        return [SourceDocument(**row) for row in payload]
