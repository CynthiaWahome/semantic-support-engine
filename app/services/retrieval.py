"""RAG-first retrieval with the existing keyword knowledge-base fallback."""

from __future__ import annotations

from collections.abc import Sequence

from app.integrations.embeddings import EmbeddingProvider
from app.repositories.retrieval import FaissVectorRepository
from app.schemas.knowledge_base import AnswerResponse
from app.schemas.retrieval import RetrievalDocument, RetrievedDocument
from app.services.knowledge_base import KnowledgeBaseService
from app.services.rag_safeguards import (
    RATE_LIMIT_MESSAGE,
    RagAdminNotifier,
    RagSafeguards,
)


class SemanticRetrievalService:
    """Build and query the persisted semantic index."""

    def __init__(
        self,
        embeddings: EmbeddingProvider,
        repository: FaissVectorRepository,
        minimum_score: float = 0.6,
    ) -> None:
        if not 0.0 <= minimum_score <= 1.0:
            raise ValueError("minimum_score must be between 0 and 1")
        self.embeddings = embeddings
        self.repository = repository
        self.minimum_score = minimum_score

    def rebuild(self, documents: Sequence[RetrievalDocument]) -> None:
        """Embed question-answer pairs and replace the persisted index."""
        vectors = [
            self.embeddings.embed(f"{document.question} {document.answer}")
            for document in documents
        ]
        self.repository.replace(documents, vectors)

    def retrieve(self, question: str, limit: int = 3) -> list[RetrievedDocument]:
        """Return confident matches from the persisted FAISS index."""
        if not question.strip():
            raise ValueError("question must not be blank")
        results = self.repository.search(self.embeddings.embed(question), limit)
        return [result for result in results if result.score >= self.minimum_score]


class RagKnowledgeBaseService:
    """Try curated semantic answers first, then preserve keyword behavior."""

    def __init__(
        self,
        retrieval: SemanticRetrievalService,
        keyword_service: KnowledgeBaseService,
        safeguards: RagSafeguards | None = None,
        notifier: RagAdminNotifier | None = None,
    ) -> None:
        self.retrieval = retrieval
        self.keyword_service = keyword_service
        self.safeguards = safeguards
        self.notifier = notifier

    def answer(
        self,
        question: str,
        user_id: str = "",
        channel: str = "",
        request_id: str = "",
    ) -> AnswerResponse:
        """Return the best semantic answer or delegate to keyword matching."""
        if self.safeguards and not user_id:
            raise ValueError("user_id is required when RAG safeguards are enabled")
        if self.safeguards and self.safeguards.is_blocked(question):
            self._notify(question, user_id, channel, "blocked topic")
            return AnswerResponse(
                answer=self.keyword_service.fallback,
                source="fallback",
            )
        if self.safeguards and self.safeguards.is_rate_limited(user_id, request_id):
            self._notify(question, user_id, channel, "rate limited")
            return AnswerResponse(answer=RATE_LIMIT_MESSAGE, source="fallback")
        if self.safeguards:
            cached = self.safeguards.get_cached(question)
            if cached is not None:
                return AnswerResponse(answer=cached, source="semantic_retrieval")
        try:
            matches = self.retrieval.retrieve(question)
        except (FileNotFoundError, OSError, ValueError):
            matches = []
        if matches:
            if self.safeguards:
                self.safeguards.cache(question, matches[0].document.answer)
            return AnswerResponse(
                answer=matches[0].document.answer,
                source="semantic_retrieval",
            )
        self._notify(question, user_id, channel, "unanswered question")
        return self.keyword_service.answer(question)

    def _notify(self, question: str, user_id: str, channel: str, reason: str) -> None:
        """Send an optional notification without breaking the answer path."""
        if self.notifier is None:
            return
        try:
            self.notifier.notify(question, user_id, channel, reason)
        except Exception:  # noqa: BLE001 — notification must not block answering
            return


def as_retrieval_document(
    record: dict[str, object], position: int
) -> RetrievalDocument:
    """Convert a cleaned scraper record into an indexable document."""
    question = str(record.get("question") or "").strip()
    answer = str(record.get("answer") or "").strip()
    if not question or not answer:
        raise ValueError(f"record {position} must contain question and answer")
    document_id = str(record.get("thread_ts") or f"record-{position}")
    source = str(record.get("source_channel") or "curated-dataset")
    return RetrievalDocument(
        document_id=document_id,
        question=question,
        answer=answer,
        source=source,
        metadata={"position": str(position)},
    )
