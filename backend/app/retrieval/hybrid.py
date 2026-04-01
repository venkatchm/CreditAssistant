from __future__ import annotations

from app.retrieval.embeddings import EmbeddingProvider
from app.retrieval.lexical_store import LexicalIndex
from app.retrieval.models import RetrievedChunk, RetrievalCandidate
from app.retrieval.reranker import Reranker
from app.retrieval.vector_store import VectorStore


class HybridRetriever:
    def __init__(
        self,
        embedding_provider: EmbeddingProvider,
        vector_store: VectorStore,
        lexical_index: LexicalIndex,
        reranker: Reranker,
        vector_weight: float = 0.55,
        lexical_weight: float = 0.45,
    ) -> None:
        self.embedding_provider = embedding_provider
        self.vector_store = vector_store
        self.lexical_index = lexical_index
        self.reranker = reranker
        self.vector_weight = vector_weight
        self.lexical_weight = lexical_weight

    def search(self, query: str, top_k: int = 3) -> list[RetrievedChunk]:
        query_embedding = self.embedding_provider.embed(query)
        vector_hits = self.vector_store.search(query_embedding, top_k=top_k * 2)
        lexical_hits = self.lexical_index.search(query, top_k=top_k * 2)
        merged = self._merge_candidates(vector_hits, lexical_hits)
        reranked = self.reranker.rerank(query, merged, top_k=top_k)
        return [
            RetrievedChunk(
                chunk_id=item.chunk.chunk_id,
                doc_id=item.chunk.doc_id,
                topic=item.chunk.topic,
                title=item.chunk.title,
                content=item.chunk.content,
                source=item.chunk.source,
                score=round(item.score, 4),
                strategy=item.strategy,
                score_breakdown=item.score_breakdown,
                effective_date=item.chunk.effective_date,
                version=item.chunk.version,
            )
            for item in reranked
        ]

    def _merge_candidates(
        self,
        vector_hits: list[RetrievalCandidate],
        lexical_hits: list[RetrievalCandidate],
    ) -> list[RetrievalCandidate]:
        by_chunk_id: dict[str, RetrievalCandidate] = {}
        for candidate in vector_hits:
            weighted_score = candidate.score * self.vector_weight
            by_chunk_id[candidate.chunk.chunk_id] = candidate.model_copy(
                update={
                    "score": weighted_score,
                    "strategy": "hybrid",
                    "score_breakdown": {
                        "vector": round(candidate.score, 4),
                        "weighted_vector": round(weighted_score, 4),
                    },
                }
            )
        for candidate in lexical_hits:
            weighted_score = candidate.score * self.lexical_weight
            existing = by_chunk_id.get(candidate.chunk.chunk_id)
            if existing is None:
                by_chunk_id[candidate.chunk.chunk_id] = candidate.model_copy(
                    update={
                        "score": weighted_score,
                        "strategy": "hybrid",
                        "score_breakdown": {
                            "lexical": round(candidate.score, 4),
                            "weighted_lexical": round(weighted_score, 4),
                        },
                    }
                )
                continue
            existing.score += weighted_score
            existing.score_breakdown["lexical"] = round(candidate.score, 4)
            existing.score_breakdown["weighted_lexical"] = round(weighted_score, 4)
        merged = list(by_chunk_id.values())
        merged.sort(key=lambda item: item.score, reverse=True)
        return merged
