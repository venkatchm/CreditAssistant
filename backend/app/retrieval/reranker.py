from __future__ import annotations

from abc import ABC, abstractmethod

from app.retrieval.lexical_store import tokenize
from app.retrieval.models import RetrievalCandidate


class Reranker(ABC):
    @abstractmethod
    def rerank(self, query: str, candidates: list[RetrievalCandidate], top_k: int) -> list[RetrievalCandidate]:
        raise NotImplementedError


class SimpleReranker(Reranker):
    def rerank(self, query: str, candidates: list[RetrievalCandidate], top_k: int) -> list[RetrievalCandidate]:
        query_terms = set(tokenize(query))
        reranked: list[RetrievalCandidate] = []
        for candidate in candidates:
            title_terms = set(tokenize(candidate.chunk.title))
            topic_terms = set(tokenize(candidate.chunk.topic.replace("_", " ")))
            boost = 0.15 if query_terms & title_terms else 0.0
            boost += 0.1 if query_terms & topic_terms else 0.0
            combined = candidate.score + boost
            reranked.append(
                candidate.model_copy(
                    update={
                        "score": combined,
                        "score_breakdown": {
                            **candidate.score_breakdown,
                            "rerank_boost": round(boost, 4),
                        },
                    }
                )
            )
        reranked.sort(key=lambda item: item.score, reverse=True)
        return reranked[:top_k]
