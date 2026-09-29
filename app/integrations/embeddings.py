"""Embedding-provider boundaries and a deterministic local implementation."""

from __future__ import annotations

import hashlib
import itertools
import math
import re
from collections.abc import Sequence
from typing import Protocol

TOKEN_PATTERN = re.compile(r"[\w']+", re.UNICODE)


class EmbeddingProvider(Protocol):
    """Provider boundary for local or hosted text embeddings."""

    @property
    def dimension(self) -> int:
        """Return the fixed vector length produced by this provider."""
        ...

    def embed(self, text: str) -> tuple[float, ...]:
        """Embed one non-empty text value into a fixed-size vector."""
        ...


class HashEmbeddingProvider:
    """Deterministic local baseline for tests and offline development.

    This is a retrieval seam, not a claim of model-quality semantic search. A
    hosted embedding provider can implement ``EmbeddingProvider`` later while
    the repository and service remain unchanged.
    """

    def __init__(self, dimension: int = 128) -> None:
        if dimension < 2:
            raise ValueError("embedding dimension must be at least 2")
        self._dimension = dimension

    @property
    def dimension(self) -> int:
        """Return the configured vector length."""
        return self._dimension

    def embed(self, text: str) -> tuple[float, ...]:
        """Create a normalized token and bigram feature vector."""
        tokens = [token.lower() for token in TOKEN_PATTERN.findall(text)]
        if not tokens:
            raise ValueError("cannot embed blank text")
        features: Sequence[str] = (
            *tokens,
            *(f"{left} {right}" for left, right in itertools.pairwise(tokens)),
        )
        vector = [0.0] * self._dimension
        for feature in features:
            digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
            index = int.from_bytes(digest[:4], "big") % self._dimension
            sign = 1.0 if digest[4] % 2 else -1.0
            vector[index] += sign
        magnitude = math.sqrt(sum(value * value for value in vector))
        return tuple(value / magnitude for value in vector)
