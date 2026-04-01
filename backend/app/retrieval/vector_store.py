from __future__ import annotations

from abc import ABC, abstractmethod
from math import sqrt

from app.retrieval.models import ChunkedDocument, RetrievalCandidate


class VectorStore(ABC):
    @abstractmethod
    def index(self, chunks: list[ChunkedDocument], embeddings: list[list[float]]) -> None:
        raise NotImplementedError

    @abstractmethod
    def search(self, query_embedding: list[float], top_k: int) -> list[RetrievalCandidate]:
        raise NotImplementedError


class InMemoryVectorStore(VectorStore):
    def __init__(self) -> None:
        self._rows: list[tuple[ChunkedDocument, list[float]]] = []

    def index(self, chunks: list[ChunkedDocument], embeddings: list[list[float]]) -> None:
        self._rows = list(zip(chunks, embeddings))

    def search(self, query_embedding: list[float], top_k: int) -> list[RetrievalCandidate]:
        ranked = []
        for chunk, embedding in self._rows:
            score = cosine_similarity(query_embedding, embedding)
            ranked.append(
                RetrievalCandidate(
                    chunk=chunk,
                    score=score,
                    strategy="vector",
                    score_breakdown={"vector": round(score, 4)},
                )
            )
        ranked.sort(key=lambda item: item.score, reverse=True)
        return ranked[:top_k]


class PgVectorStore(VectorStore):
    def index(self, chunks: list[ChunkedDocument], embeddings: list[list[float]]) -> None:
        raise NotImplementedError("PgVectorStore wiring is not configured yet.")

    def search(self, query_embedding: list[float], top_k: int) -> list[RetrievalCandidate]:
        raise NotImplementedError("PgVectorStore wiring is not configured yet.")


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right:
        return 0.0
    numerator = sum(lhs * rhs for lhs, rhs in zip(left, right))
    left_norm = sqrt(sum(value * value for value in left)) or 1.0
    right_norm = sqrt(sum(value * value for value in right)) or 1.0
    return numerator / (left_norm * right_norm)
