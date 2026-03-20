from __future__ import annotations

import json
from pathlib import Path

from app.retrieval.chunking import SentenceChunker
from app.retrieval.embeddings import EmbeddingProvider
from app.retrieval.models import ChunkedDocument, SourceDocument
from app.retrieval.sqlite_store import RetrievalPersistence


class JsonKnowledgeIngestionPipeline:
    def __init__(
        self,
        knowledge_path: Path,
        chunker: SentenceChunker,
        embedding_provider: EmbeddingProvider,
        persistence: RetrievalPersistence,
    ) -> None:
        self.knowledge_path = knowledge_path
        self.chunker = chunker
        self.embedding_provider = embedding_provider
        self.persistence = persistence

    def ingest(self) -> list[ChunkedDocument]:
        documents = self._load_documents()
        chunks = [chunk for document in documents for chunk in self.chunker.chunk(document)]
        embeddings = [self.embedding_provider.embed(self._embedding_text(chunk)) for chunk in chunks]
        self.persistence.replace_documents(documents=documents, chunks=chunks, embeddings=embeddings)
        return chunks

    def _load_documents(self) -> list[SourceDocument]:
        with self.knowledge_path.open("r", encoding="utf-8") as file:
            payload = json.load(file)
        return [SourceDocument(**row) for row in payload]

    def _embedding_text(self, chunk: ChunkedDocument) -> str:
        return " ".join([chunk.title, chunk.topic.replace("_", " "), chunk.content, " ".join(chunk.tags)])
