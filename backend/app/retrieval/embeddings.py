from __future__ import annotations

from abc import ABC, abstractmethod
from hashlib import sha256
from math import sqrt


class EmbeddingProvider(ABC):
    @abstractmethod
    def embed(self, text: str) -> list[float]:
        raise NotImplementedError


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
