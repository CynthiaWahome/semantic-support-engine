"""Tests for the persisted semantic retrieval and fallback flow."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from app.integrations.embeddings import HuggingFaceEmbeddingProvider
from app.repositories.retrieval import FaissVectorRepository
from app.schemas.knowledge_base import KnowledgeTopic
from app.schemas.retrieval import RetrievalDocument
from app.services.knowledge_base import KnowledgeBaseService
from app.services.retrieval import (
    RagKnowledgeBaseService,
    SemanticRetrievalService,
    as_retrieval_document,
)


class FakeEmbeddings:
    """Deterministic provider used to test persistence without network calls."""

    def embed(self, text: str) -> np.ndarray:
        """Place access and billing fixtures on separate axes."""
        return np.array(
            [1.0, 0.0] if "access" in text.lower() else [0.0, 1.0],
            dtype="float32",
        )


class MemoryRepository:
    """Minimal keyword repository for fallback tests."""

    def get_all_topics(self):
        return {
            "access": KnowledgeTopic(
                keywords=["access"], answer="Use the account portal."
            )
        }

    def set_all_topics(self, topics):
        raise NotImplementedError


def document(document_id: str, question: str, answer: str) -> RetrievalDocument:
    """Build a retrieval fixture."""
    return RetrievalDocument(
        document_id=document_id,
        question=question,
        answer=answer,
        source="reviewed-slack-dataset",
    )


def service(tmp_path: Path) -> SemanticRetrievalService:
    """Provide a retrieval service backed by temporary FAISS artifacts."""
    repository = FaissVectorRepository(
        tmp_path / "kb_index.faiss", tmp_path / "kb_index_records.json"
    )
    return SemanticRetrievalService(FakeEmbeddings(), repository, minimum_score=0.6)


def test_rebuild_persists_and_reloads_index(tmp_path: Path):
    """Persist vectors and retrieve them after constructing a new repository."""
    first_service = service(tmp_path)
    first_service.rebuild(
        [
            document("access", "How do I access my account?", "Use the portal."),
            document("billing", "Where is my invoice?", "Open billing history."),
        ]
    )

    second_service = service(tmp_path)
    results = second_service.retrieve("I need account access")

    assert results[0].document.document_id == "access"
    assert results[0].score == pytest.approx(1.0)


def test_rag_falls_back_to_keyword_service_when_no_confident_match(tmp_path: Path):
    """Preserve the original keyword answer when RAG has no confident result."""
    rag = RagKnowledgeBaseService(
        service(tmp_path), KnowledgeBaseService(MemoryRepository())
    )

    response = rag.answer("How do I get access?")

    assert response.answer == "Use the account portal."
    assert response.source == "knowledge_base"


def test_rag_returns_semantic_answer_when_index_matches(tmp_path: Path):
    """Return the curated semantic answer before keyword matching."""
    retrieval = service(tmp_path)
    retrieval.rebuild(
        [document("access", "How do I access my account?", "Use the new portal.")]
    )
    rag = RagKnowledgeBaseService(retrieval, KnowledgeBaseService(MemoryRepository()))

    response = rag.answer("I need account access")

    assert response.answer == "Use the new portal."
    assert response.source == "semantic_retrieval"


def test_missing_index_falls_back_without_raising(tmp_path: Path):
    """Treat missing build artifacts as a safe RAG miss."""
    rag = RagKnowledgeBaseService(
        service(tmp_path), KnowledgeBaseService(MemoryRepository())
    )

    assert rag.answer("How do I get access?").source == "knowledge_base"


def test_hugging_face_provider_normalizes_response():
    """Use the configured model endpoint and normalize its returned vector."""
    response = MagicMock()
    response.json.return_value = [1.0, 2.0, 3.0]
    provider = HuggingFaceEmbeddingProvider("hf-test-token")

    with patch(
        "app.integrations.embeddings.requests.post", return_value=response
    ) as post:
        vector = provider.embed("How do I sign in?")

    response.raise_for_status.assert_called_once_with()
    post.assert_called_once_with(
        provider.endpoint,
        headers={"Authorization": "Bearer hf-test-token"},
        json={"inputs": "How do I sign in?"},
        timeout=15.0,
    )
    assert np.linalg.norm(vector) == pytest.approx(1.0)


def test_dataset_record_becomes_retrieval_document():
    """Preserve the scraper thread and channel as retrieval metadata."""
    result = as_retrieval_document(
        {
            "thread_ts": "1700000000.000000",
            "source_channel": "support-general",
            "question": "How do I sign in?",
            "answer": "Use the portal.",
        },
        4,
    )

    assert result.document_id == "1700000000.000000"
    assert result.source == "support-general"
