from __future__ import annotations

from abc import ABC, abstractmethod
from collections import Counter

from app.retrieval.models import ChunkedDocument, RetrievalCandidate


class LexicalIndex(ABC):
    @abstractmethod
    def index(self, chunks: list[ChunkedDocument]) -> None:
        raise NotImplementedError

    @abstractmethod
    def search(self, query: str, top_k: int) -> list[RetrievalCandidate]:
        raise NotImplementedError


class InMemoryLexicalIndex(LexicalIndex):
    def __init__(self) -> None:
        self._chunks: list[tuple[ChunkedDocument, Counter[str]]] = []

    def index(self, chunks: list[ChunkedDocument]) -> None:
        self._chunks = [(chunk, Counter(tokenize(build_search_text(chunk)))) for chunk in chunks]

    def search(self, query: str, top_k: int) -> list[RetrievalCandidate]:
        query_terms = tokenize(query)
        if not query_terms:
            return []
        ranked: list[RetrievalCandidate] = []
        for chunk, frequencies in self._chunks:
            overlap = sum(frequencies.get(term, 0) for term in query_terms)
            if overlap <= 0:
                continue
            normalized_score = overlap / max(len(query_terms), 1)
            ranked.append(
                RetrievalCandidate(
                    chunk=chunk,
                    score=normalized_score,
                    strategy="lexical",
                    score_breakdown={"lexical": round(normalized_score, 4)},
                )
            )
        ranked.sort(key=lambda item: item.score, reverse=True)
        return ranked[:top_k]


def build_search_text(chunk: ChunkedDocument) -> str:
    return " ".join([chunk.topic, chunk.title, chunk.content, " ".join(chunk.tags)])


def tokenize(text: str) -> list[str]:
    cleaned = "".join(character.lower() if character.isalnum() or character.isspace() else " " for character in text)
    return [token for token in cleaned.split() if token]
