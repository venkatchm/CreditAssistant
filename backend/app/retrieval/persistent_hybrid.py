from __future__ import annotations

from app.retrieval.embeddings import EmbeddingProvider
from app.retrieval.models import RetrievedChunk
from app.retrieval.sqlite_store import RetrievalPersistence


class PersistentHybridRetriever:
    def __init__(
        self,
        embedding_provider: EmbeddingProvider,
        persistence: RetrievalPersistence,
        vector_weight: float = 0.55,
        lexical_weight: float = 0.45,
    ) -> None:
        self.embedding_provider = embedding_provider
        self.persistence = persistence
        self.vector_weight = vector_weight
        self.lexical_weight = lexical_weight

    def search(self, query: str, top_k: int = 3) -> list[RetrievedChunk]:
        query_embedding = self.embedding_provider.embed(query)
        vector_hits = self.persistence.vector_search(query_embedding=query_embedding, top_k=top_k * 3)
        lexical_hits = self.persistence.lexical_search(query=query, top_k=top_k * 3)
        merged = self._merge(vector_hits=vector_hits, lexical_hits=lexical_hits)
        reranked = self._rerank(query=query, chunks=merged)
        return reranked[:top_k]

    def _merge(self, vector_hits: list[RetrievedChunk], lexical_hits: list[RetrievedChunk]) -> list[RetrievedChunk]:
        by_chunk_id: dict[str, RetrievedChunk] = {}
        for item in vector_hits:
            weighted = item.score * self.vector_weight
            by_chunk_id[item.chunk_id] = item.model_copy(
                update={
                    "score": weighted,
                    "strategy": "hybrid",
                    "score_breakdown": {
                        "vector": round(item.score, 4),
                        "weighted_vector": round(weighted, 4),
                    },
                }
            )
        for item in lexical_hits:
            weighted = item.score * self.lexical_weight
            existing = by_chunk_id.get(item.chunk_id)
            if existing is None:
                by_chunk_id[item.chunk_id] = item.model_copy(
                    update={
                        "score": weighted,
                        "strategy": "hybrid",
                        "score_breakdown": {
                            "lexical": round(item.score, 4),
                            "weighted_lexical": round(weighted, 4),
                        },
                    }
                )
                continue
            existing.score += weighted
            existing.score_breakdown["lexical"] = round(item.score, 4)
            existing.score_breakdown["weighted_lexical"] = round(weighted, 4)
        merged = list(by_chunk_id.values())
        merged.sort(key=lambda item: item.score, reverse=True)
        return merged

    def _rerank(self, query: str, chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
        query_terms = set(_tokenize(query))
        reranked: list[RetrievedChunk] = []
        for item in chunks:
            title_terms = set(_tokenize(item.title))
            topic_terms = set(_tokenize(item.topic.replace("_", " ")))
            boost = 0.15 if query_terms & title_terms else 0.0
            boost += 0.1 if query_terms & topic_terms else 0.0
            reranked.append(
                item.model_copy(
                    update={
                        "score": item.score + boost,
                        "score_breakdown": {
                            **item.score_breakdown,
                            "rerank_boost": round(boost, 4),
                        },
                    }
                )
            )
        reranked.sort(key=lambda item: item.score, reverse=True)
        return reranked


def _tokenize(text: str) -> list[str]:
    cleaned = "".join(character.lower() if character.isalnum() or character.isspace() else " " for character in text)
    return [token for token in cleaned.split() if token]
