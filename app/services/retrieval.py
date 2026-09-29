"""Semantic retrieval service for curated support answers."""

from __future__ import annotations

from collections.abc import Sequence

from app.integrations.embeddings import EmbeddingProvider
from app.repositories.retrieval import InMemoryVectorRepository
from app.schemas.retrieval import RetrievalDocument, RetrievedDocument


class SemanticRetrievalService:
    """Index support documents and retrieve relevant answers by similarity."""

    def __init__(
        self,
        embeddings: EmbeddingProvider,
        repository: InMemoryVectorRepository,
        minimum_score: float = 0.35,
    ) -> None:
        if not 0.0 <= minimum_score <= 1.0:
            raise ValueError("minimum_score must be between 0 and 1")
        if embeddings.dimension != repository.dimension:
            raise ValueError("embedding and repository dimensions must match")
        self.embeddings = embeddings
        self.repository = repository
        self.minimum_score = minimum_score

    def rebuild(self, documents: Sequence[RetrievalDocument]) -> None:
        """Embed and atomically replace the complete retrieval index."""
        records = [
            (document, self.embeddings.embed(self._search_text(document)))
            for document in documents
        ]
        self.repository.replace(records)

    def retrieve(self, question: str, limit: int = 3) -> list[RetrievedDocument]:
        """Return only documents above the configured confidence threshold."""
        if not question.strip():
            raise ValueError("question must not be blank")
        results = self.repository.search(self.embeddings.embed(question), limit)
        return [result for result in results if result.score >= self.minimum_score]

    @staticmethod
    def _search_text(document: RetrievalDocument) -> str:
        """Embed both the source question and answer for better recall."""
        return f"{document.question}\n{document.answer}"
