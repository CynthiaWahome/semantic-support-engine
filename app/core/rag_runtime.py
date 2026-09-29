"""Runtime configuration and dependency composition for the RAG service."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from upstash_redis import Redis

from app.core.knowledge_base import get_knowledge_base_service
from app.core.rag_constants import DEFAULT_BLOCKED_TOPICS
from app.integrations.embeddings import EmbeddingProvider, HuggingFaceEmbeddingProvider
from app.integrations.rag_state import (
    InMemoryRagStateStore,
    RagStateStore,
    UpstashRagStateStore,
)
from app.repositories.retrieval import FaissVectorRepository
from app.services.knowledge_base import KnowledgeBaseService
from app.services.rag_safeguards import RagAdminNotifier, RagSafeguards
from app.services.retrieval import RagKnowledgeBaseService, SemanticRetrievalService


@dataclass(frozen=True)
class RagRuntimeConfig:
    """Provider-neutral settings used to compose one RAG service."""

    index_path: Path = Path("data/kb_index.faiss")
    records_path: Path = Path("data/kb_index_records.json")
    embedding_model: str = "sentence-transformers/all-mpnet-base-v2"
    minimum_score: float = 0.6
    state_backend: str = "memory"
    blocked_topics: tuple[str, ...] = DEFAULT_BLOCKED_TOPICS
    embedding_token: str | None = None
    upstash_url: str | None = None
    upstash_token: str | None = None

    @classmethod
    def from_mapping(cls, settings: Mapping[str, str]) -> RagRuntimeConfig:
        """Build settings from an injected deployment configuration mapping."""
        minimum_score_text = settings.get("RAG_MIN_SIMILARITY", "0.6")
        try:
            minimum_score = float(minimum_score_text)
        except ValueError as error:
            raise ValueError("RAG_MIN_SIMILARITY must be a number") from error
        if not math.isfinite(minimum_score) or not 0.0 <= minimum_score <= 1.0:
            raise ValueError("RAG_MIN_SIMILARITY must be between 0 and 1")
        state_backend = settings.get("RAG_STATE_BACKEND", "memory").strip().lower()
        if state_backend not in {"memory", "upstash", "none"}:
            raise ValueError("RAG_STATE_BACKEND must be memory, upstash, or none")
        return cls(
            index_path=Path(settings.get("RAG_INDEX_PATH", "data/kb_index.faiss")),
            records_path=Path(
                settings.get("RAG_RECORDS_PATH", "data/kb_index_records.json")
            ),
            embedding_model=settings.get(
                "HF_EMBED_MODEL", "sentence-transformers/all-mpnet-base-v2"
            ),
            minimum_score=minimum_score,
            state_backend=state_backend,
            embedding_token=settings.get("HF_TOKEN"),
            upstash_url=settings.get("UPSTASH_REDIS_REST_URL"),
            upstash_token=settings.get("UPSTASH_REDIS_REST_TOKEN"),
        )


def create_state_store(config: RagRuntimeConfig) -> RagStateStore | None:
    """Create the configured local, shared, or disabled state boundary."""
    if config.state_backend == "none":
        return None
    if config.state_backend == "memory":
        return InMemoryRagStateStore()
    url = (config.upstash_url or "").strip()
    token = (config.upstash_token or "").strip()
    if not url or not token:
        raise ValueError(
            "UPSTASH_REDIS_REST_URL and UPSTASH_REDIS_REST_TOKEN are required"
        )
    return UpstashRagStateStore(Redis(url=url, token=token))


def create_rag_service(
    *,
    config: RagRuntimeConfig | None = None,
    keyword_service: KnowledgeBaseService | None = None,
    embeddings: EmbeddingProvider | None = None,
    repository: FaissVectorRepository | None = None,
    state: RagStateStore | None = None,
    notifier: RagAdminNotifier | None = None,
) -> RagKnowledgeBaseService:
    """Compose semantic retrieval, fallback, and optional safeguards.

    When both ``config`` and ``state`` are omitted, local in-memory safeguards
    are enabled. Passing ``state=None`` does not disable safeguards; use
    ``RagRuntimeConfig(state_backend="none")`` to disable them explicitly.
    """
    runtime_config = config or RagRuntimeConfig()
    keyword = keyword_service or get_knowledge_base_service()
    embedding_provider = embeddings or _create_embedding_provider(runtime_config)
    vector_repository = repository or FaissVectorRepository(
        runtime_config.index_path,
        runtime_config.records_path,
    )
    state_store = state if state is not None else create_state_store(runtime_config)
    safeguards = (
        RagSafeguards(state_store, blocked_topics=runtime_config.blocked_topics)
        if state_store is not None
        else None
    )
    retrieval = SemanticRetrievalService(
        embedding_provider,
        vector_repository,
        minimum_score=runtime_config.minimum_score,
    )
    return RagKnowledgeBaseService(
        retrieval,
        keyword,
        safeguards=safeguards,
        notifier=notifier,
    )


def _create_embedding_provider(config: RagRuntimeConfig) -> EmbeddingProvider:
    """Create the configured hosted embedding provider without logging its token."""
    token = config.embedding_token or ""
    if not token:
        raise ValueError("HF_TOKEN must be provided by the runtime configuration")
    return HuggingFaceEmbeddingProvider(token=token, model=config.embedding_model)
