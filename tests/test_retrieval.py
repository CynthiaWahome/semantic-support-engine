"""Tests for the semantic retrieval foundation."""

import pytest

from app.integrations.embeddings import HashEmbeddingProvider
from app.repositories.retrieval import InMemoryVectorRepository
from app.schemas.retrieval import RetrievalDocument
from app.services.retrieval import SemanticRetrievalService


def document(document_id: str, question: str, answer: str) -> RetrievalDocument:
    """Build a minimal retrieval fixture."""
    return RetrievalDocument(
        document_id=document_id,
        question=question,
        answer=answer,
        source="reviewed-slack-dataset",
    )


@pytest.fixture
def service() -> SemanticRetrievalService:
    """Provide a deterministic local retrieval service."""
    embeddings = HashEmbeddingProvider(dimension=64)
    return SemanticRetrievalService(
        embeddings,
        InMemoryVectorRepository(dimension=64),
        minimum_score=0.2,
    )


def test_rebuild_and_retrieve_returns_relevant_document(service):
    """Retrieve the matching support answer before unrelated content."""
    service.rebuild(
        [
            document("access", "How do I sign in?", "Use the account portal."),
            document(
                "billing", "Where can I find my invoice?", "Open billing history."
            ),
        ]
    )

    results = service.retrieve("I cannot log in to my account")

    assert results
    assert results[0].document.document_id == "access"
    assert results[0].score >= 0.2


def test_rebuild_replaces_previous_documents(service):
    """Prevent stale answers from surviving a complete index rebuild."""
    service.rebuild([document("old", "How do I sign in?", "Old answer")])
    service.rebuild([document("new", "Where is the invoice?", "New answer")])

    results = service.retrieve("How do I sign in?", limit=3)

    assert all(result.document.document_id == "new" for result in results)


def test_low_confidence_results_use_empty_retrieval(service):
    """Return no context when similarity is below the confidence threshold."""
    service.rebuild([document("access", "How do I sign in?", "Use the portal.")])

    assert service.retrieve("What is the weather today?") == []


def test_retrieval_rejects_invalid_dimensions():
    """Fail during construction when the index cannot accept provider vectors."""
    with pytest.raises(ValueError, match="dimensions must match"):
        SemanticRetrievalService(
            HashEmbeddingProvider(dimension=64),
            InMemoryVectorRepository(dimension=32),
        )
