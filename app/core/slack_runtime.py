"""Deployment composition for the Slack RAG application."""

from __future__ import annotations

from collections.abc import Mapping

from slack_bolt import App
from slack_sdk.web.client import WebClient

from app.core.rag_runtime import RagRuntimeConfig, create_rag_service
from app.integrations.embeddings import EmbeddingProvider
from app.integrations.rag_state import RagStateStore
from app.integrations.slack_bolt import create_slack_app
from app.repositories.retrieval import FaissVectorRepository
from app.services.knowledge_base import KnowledgeBaseService
from app.services.rag_safeguards import RagAdminNotifier, SlackRagAdminNotifier
from app.services.slack_answering import SlackAnsweringService


def create_configured_slack_service(
    settings: Mapping[str, str],
    *,
    keyword_service: KnowledgeBaseService | None = None,
    embeddings: EmbeddingProvider | None = None,
    repository: FaissVectorRepository | None = None,
    state: RagStateStore | None = None,
    notifier: RagAdminNotifier | None = None,
) -> SlackAnsweringService:
    """Compose the RAG answer service from injected deployment settings.

    Settings are supplied by the deployment entry point rather than read from
    ``.env`` here. This keeps the application independent of Slack, hosting,
    and configuration-loading choices while allowing tests to inject fakes.
    """
    config = RagRuntimeConfig.from_mapping(settings)
    configured_notifier = notifier
    admin_channel = settings.get("SLACK_ADMIN_CHANNEL", "").strip()
    if configured_notifier is None and admin_channel:
        bot_token = settings.get("SLACK_BOT_TOKEN", "").strip()
        if not bot_token:
            raise ValueError(
                "SLACK_BOT_TOKEN is required when SLACK_ADMIN_CHANNEL is configured"
            )
        configured_notifier = SlackRagAdminNotifier(
            WebClient(token=bot_token), admin_channel
        )

    rag_service = create_rag_service(
        config=config,
        keyword_service=keyword_service,
        embeddings=embeddings,
        repository=repository,
        state=state,
        notifier=configured_notifier,
    )
    return SlackAnsweringService(
        rag_service,
        bot_user_id=settings.get("SLACK_BOT_USER_ID") or None,
    )


def create_configured_slack_app(
    settings: Mapping[str, str],
    *,
    keyword_service: KnowledgeBaseService | None = None,
    embeddings: EmbeddingProvider | None = None,
    repository: FaissVectorRepository | None = None,
    state: RagStateStore | None = None,
    notifier: RagAdminNotifier | None = None,
    token_verification_enabled: bool = False,
) -> App:
    """Compose the configured RAG service and Slack Bolt event application."""
    bot_token = _required_setting(settings, "SLACK_BOT_TOKEN")
    signing_secret = _required_setting(settings, "SLACK_SIGNING_SECRET")
    service = create_configured_slack_service(
        settings,
        keyword_service=keyword_service,
        embeddings=embeddings,
        repository=repository,
        state=state,
        notifier=notifier,
    )
    return create_slack_app(
        service,
        token=bot_token,
        signing_secret=signing_secret,
        token_verification_enabled=token_verification_enabled,
    )


def _required_setting(settings: Mapping[str, str], name: str) -> str:
    """Return a non-blank deployment setting without exposing its value."""
    value = settings.get(name, "").strip()
    if not value:
        raise ValueError(f"{name} must be provided")
    return value
