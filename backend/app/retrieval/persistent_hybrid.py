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
        vector_hits = self.persistence.vector_search(query_embedding=query_embedding, top_k=top_k * 5)
        lexical_hits = self.persistence.lexical_search(query=query, top_k=top_k * 5)
        merged = self._rrf_merge(vector_hits=vector_hits, lexical_hits=lexical_hits)
        boosted = self._title_topic_boost(query=query, chunks=merged)
        return boosted[:top_k]

    def _rrf_merge(
        self,
        vector_hits: list[RetrievedChunk],
        lexical_hits: list[RetrievedChunk],
        k: int = 60,
    ) -> list[RetrievedChunk]:
        """Reciprocal Rank Fusion — merges rankings by position, not raw score."""
        rrf_scores: dict[str, float] = {}
        chunk_map: dict[str, RetrievedChunk] = {}
        vector_ranks: dict[str, int] = {}
        lexical_ranks: dict[str, int] = {}

        for rank, hit in enumerate(vector_hits):
            rrf_scores[hit.chunk_id] = rrf_scores.get(hit.chunk_id, 0.0) + 1.0 / (k + rank + 1)
            chunk_map[hit.chunk_id] = hit
            vector_ranks[hit.chunk_id] = rank + 1

        for rank, hit in enumerate(lexical_hits):
            rrf_scores[hit.chunk_id] = rrf_scores.get(hit.chunk_id, 0.0) + 1.0 / (k + rank + 1)
            if hit.chunk_id not in chunk_map:
                chunk_map[hit.chunk_id] = hit
            lexical_ranks[hit.chunk_id] = rank + 1

        ranked = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)
        return [
            chunk_map[chunk_id].model_copy(
                update={
                    "score": score,
                    "strategy": "hybrid_rrf",
                    "score_breakdown": {
                        "rrf": round(score, 4),
                        "vector_rank": vector_ranks.get(chunk_id),
                        "lexical_rank": lexical_ranks.get(chunk_id),
                    },
                }
            )
            for chunk_id, score in ranked
        ]

    def _title_topic_boost(self, query: str, chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
        """Small boost for chunks whose title/topic matches query terms."""
        query_terms = set(_tokenize(query))
        boosted: list[RetrievedChunk] = []
        for item in chunks:
            title_terms = set(_tokenize(item.title))
            topic_terms = set(_tokenize(item.topic.replace("_", " ")))
            boost = 0.005 if query_terms & title_terms else 0.0
            boost += 0.003 if query_terms & topic_terms else 0.0
            boosted.append(
                item.model_copy(
                    update={
                        "score": item.score + boost,
                        "score_breakdown": {
                            **item.score_breakdown,
                            "title_topic_boost": round(boost, 4),
                        },
                    }
                )
            )
        boosted.sort(key=lambda item: item.score, reverse=True)
        return boosted


def _tokenize(text: str) -> list[str]:
    cleaned = "".join(character.lower() if character.isalnum() or character.isspace() else " " for character in text)
    return [token for token in cleaned.split() if token]
