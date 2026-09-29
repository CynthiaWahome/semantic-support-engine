"""Tests for configurable RAG dependency composition."""

from pathlib import Path

import pytest

from app.core.rag_runtime import (
    RagRuntimeConfig,
    create_rag_service,
    create_state_store,
)
from app.integrations.rag_state import InMemoryRagStateStore
from app.schemas.knowledge_base import KnowledgeTopic
from app.services.knowledge_base import KnowledgeBaseService


class MemoryRepository:
    """Minimal keyword repository for composition tests."""

    def get_all_topics(self):
        return {
            "access": KnowledgeTopic(
                keywords=["access"], answer="Use the account portal."
            )
        }

    def set_all_topics(self, topics):
        raise NotImplementedError


class FakeEmbeddings:
    """Embedding double that avoids network calls."""

    def embed(self, text: str):
        raise AssertionError("retrieval should not run in this composition test")


def test_runtime_config_reads_injected_deployment_settings():
    """Parse deployment settings without coupling core code to an environment."""
    settings = {
        "RAG_INDEX_PATH": "tmp/index.faiss",
        "RAG_RECORDS_PATH": "tmp/records.json",
        "HF_EMBED_MODEL": "custom/model",
        "RAG_MIN_SIMILARITY": "0.72",
        "RAG_STATE_BACKEND": "none",
        "HF_TOKEN": "test-token",
    }

    config = RagRuntimeConfig.from_mapping(settings)

    assert config.index_path == Path("tmp/index.faiss")
    assert config.records_path == Path("tmp/records.json")
    assert config.embedding_model == "custom/model"
    assert config.minimum_score == pytest.approx(0.72)
    assert config.state_backend == "none"
    assert config.embedding_token == "test-token"


def test_runtime_config_rejects_unknown_state_backend():
    """Fail closed instead of silently selecting an unintended state store."""
    settings = {"RAG_STATE_BACKEND": "redis"}

    with pytest.raises(ValueError, match="RAG_STATE_BACKEND"):
        RagRuntimeConfig.from_mapping(settings)


@pytest.mark.parametrize("value", ["-0.1", "1.1", "nan", "inf", "-inf"])
def test_runtime_config_rejects_invalid_similarity_threshold(value):
    """Reject thresholds outside the valid finite similarity range."""
    with pytest.raises(ValueError, match="RAG_MIN_SIMILARITY"):
        RagRuntimeConfig.from_mapping({"RAG_MIN_SIMILARITY": value})


def test_memory_state_backend_is_available_for_local_development():
    """Use process-local state without requiring external credentials."""
    state = create_state_store(RagRuntimeConfig(state_backend="memory"))

    assert isinstance(state, InMemoryRagStateStore)


def test_upstash_state_backend_requires_both_runtime_credentials():
    """Reject incomplete shared-state configuration without exposing secrets."""
    config = RagRuntimeConfig(state_backend="upstash")

    with pytest.raises(ValueError, match="UPSTASH_REDIS_REST_URL"):
        create_state_store(config)


def test_create_rag_service_injects_local_dependencies(tmp_path: Path):
    """Compose the RAG service from injected test-safe dependencies."""
    config = RagRuntimeConfig(
        index_path=tmp_path / "index.faiss",
        records_path=tmp_path / "records.json",
        state_backend="none",
    )
    keyword_service = KnowledgeBaseService(MemoryRepository())

    service = create_rag_service(
        config=config,
        keyword_service=keyword_service,
        embeddings=FakeEmbeddings(),
    )

    assert service.keyword_service is keyword_service
    assert service.safeguards is None
