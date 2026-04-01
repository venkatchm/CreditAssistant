from __future__ import annotations

from abc import ABC, abstractmethod

from app.retrieval.models import ChunkedDocument, RetrievedChunk, SourceDocument


class RetrievalPersistenceBackend(ABC):
    @abstractmethod
    def replace_documents(
        self,
        documents: list[SourceDocument],
        chunks: list[ChunkedDocument],
        embeddings: list[list[float]],
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    def vector_search(self, query_embedding: list[float], top_k: int) -> list[RetrievedChunk]:
        raise NotImplementedError

    @abstractmethod
    def lexical_search(self, query: str, top_k: int) -> list[RetrievedChunk]:
        raise NotImplementedError

    @abstractmethod
    def has_indexed_chunks(self) -> bool:
        raise NotImplementedError
