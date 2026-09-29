"""RAG-first retrieval with the existing keyword knowledge-base fallback."""

from __future__ import annotations

from collections.abc import Sequence

from app.integrations.embeddings import EmbeddingProvider
from app.repositories.retrieval import FaissVectorRepository
from app.schemas.knowledge_base import AnswerResponse
from app.schemas.retrieval import RetrievalDocument, RetrievedDocument
from app.services.knowledge_base import KnowledgeBaseService


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
    ) -> None:
        self.retrieval = retrieval
        self.keyword_service = keyword_service

    def answer(self, question: str) -> AnswerResponse:
        """Return the best semantic answer or delegate to keyword matching."""
        try:
            matches = self.retrieval.retrieve(question)
        except (FileNotFoundError, OSError, ValueError):
            matches = []
        if matches:
            return AnswerResponse(
                answer=matches[0].document.answer,
                source="semantic_retrieval",
            )
        return self.keyword_service.answer(question)


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
