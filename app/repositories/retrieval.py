"""Vector-store boundary and an in-memory implementation for one process."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from app.schemas.retrieval import RetrievalDocument, RetrievedDocument


@dataclass(frozen=True)
class _VectorRecord:
    document: RetrievalDocument
    vector: tuple[float, ...]


class InMemoryVectorRepository:
    """Replaceable vector index for local development and deterministic tests."""

    def __init__(self, dimension: int) -> None:
        if dimension < 2:
            raise ValueError("vector dimension must be at least 2")
        self.dimension = dimension
        self._records: tuple[_VectorRecord, ...] = ()

    def replace(
        self,
        records: Sequence[tuple[RetrievalDocument, tuple[float, ...]]],
    ) -> None:
        """Atomically replace the index after validating vector dimensions."""
        validated: list[_VectorRecord] = []
        for document, vector in records:
            self._validate_vector(vector)
            validated.append(_VectorRecord(document=document, vector=vector))
        self._records = tuple(validated)

    def search(
        self, query_vector: tuple[float, ...], limit: int
    ) -> list[RetrievedDocument]:
        """Return the highest cosine-similarity documents in stable order."""
        if limit < 1:
            raise ValueError("limit must be positive")
        self._validate_vector(query_vector)
        scored = [
            RetrievedDocument(
                document=record.document,
                score=_dot_product(query_vector, record.vector),
            )
            for record in self._records
        ]
        return sorted(scored, key=lambda result: result.score, reverse=True)[:limit]

    def _validate_vector(self, vector: tuple[float, ...]) -> None:
        if len(vector) != self.dimension:
            raise ValueError(
                f"expected vector dimension {self.dimension}, got {len(vector)}"
            )
        if not all(math.isfinite(value) for value in vector):
            raise ValueError("vectors must contain only finite values")


def _dot_product(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    """Calculate cosine similarity for normalized vectors."""
    return max(-1.0, min(1.0, sum(a * b for a, b in zip(left, right))))
