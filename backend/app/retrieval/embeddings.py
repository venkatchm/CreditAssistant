from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from hashlib import sha256
from math import sqrt

logger = logging.getLogger(__name__)


class EmbeddingProvider(ABC):
    @abstractmethod
    def embed(self, text: str) -> list[float]:
        raise NotImplementedError

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple texts. Subclasses can override for batch API support."""
        return [self.embed(text) for text in texts]


class LocalHashEmbeddingProvider(EmbeddingProvider):
    def __init__(self, dimensions: int = 32) -> None:
        self.dimensions = dimensions

    def embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        normalized = " ".join(text.lower().split())
        if not normalized:
            return vector
        for token in normalized.split():
            digest = sha256(token.encode("utf-8")).digest()
            for index in range(self.dimensions):
                vector[index] += digest[index] / 255.0
        norm = sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]


class OpenAIEmbeddingProvider(EmbeddingProvider):
    """Production embedding provider using OpenAI text-embedding-3-small."""

    def __init__(
        self,
        api_key: str,
        model: str = "text-embedding-3-small",
        dimensions: int = 1536,
        batch_size: int = 100,
    ) -> None:
        import openai

        self.client = openai.OpenAI(api_key=api_key)
        self.model = model
        self.dimensions = dimensions
        self.batch_size = batch_size

    def embed(self, text: str) -> list[float]:
        response = self.client.embeddings.create(
            input=[text],
            model=self.model,
            dimensions=self.dimensions,
        )
        return response.data[0].embedding

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        all_embeddings: list[list[float]] = []
        for start in range(0, len(texts), self.batch_size):
            batch = texts[start : start + self.batch_size]
            response = self.client.embeddings.create(
                input=batch,
                model=self.model,
                dimensions=self.dimensions,
            )
            all_embeddings.extend(item.embedding for item in response.data)
        logger.info("Embedded %d texts with %s", len(texts), self.model)
        return all_embeddings
