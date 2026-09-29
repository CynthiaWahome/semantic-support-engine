"""Safe local tests for the configured Slack RAG composition."""

from unittest.mock import MagicMock

import numpy as np
import pytest

from app.core.slack_runtime import (
    create_configured_slack_app,
    create_configured_slack_service,
)
from app.integrations.rag_state import InMemoryRagStateStore
from app.integrations.slack import answer_slack_event
from app.schemas.knowledge_base import AnswerResponse, KnowledgeTopic
from app.schemas.retrieval import RetrievalDocument, RetrievedDocument
from app.services.knowledge_base import KnowledgeBaseService


class FakeEmbeddings:
    """Deterministic embedding provider for offline composition tests."""

    def embed(self, text: str) -> np.ndarray:
        """Return a fixed vector without contacting an embedding provider."""
        return np.array([1.0, 0.0], dtype="float32")


class FakeRepository:
    """Repository double returning one confident semantic match."""

    def search(self, vector: np.ndarray, limit: int = 3) -> list[RetrievedDocument]:
        """Return the fixture document regardless of the query vector."""
        return [
            RetrievedDocument(
                document=RetrievalDocument(
                    document_id="access-1",
                    question="How do I get access?",
                    answer="Use the reviewed semantic answer.",
                    source="fixture",
                ),
                score=0.99,
            )
        ]


class MemoryRepository:
    """Minimal keyword repository used by the local RAG composition test."""

    def get_all_topics(self):
        """Return one fallback topic without reading local storage."""
        return {
            "fallback": KnowledgeTopic(
                keywords=["fallback"], answer="Use the fallback answer."
            )
        }

    def set_all_topics(self, topics):
        """Accept writes required by the repository protocol."""


class RecordingNotifier:
    """Notifier double that records policy notifications in memory."""

    def __init__(self) -> None:
        """Initialize an empty notification list."""
        self.calls = []

    def notify(self, question: str, user_id: str, channel: str, reason: str) -> None:
        """Record a notification without contacting Slack."""
        self.calls.append((question, user_id, channel, reason))


def settings() -> dict[str, str]:
    """Return safe fake deployment settings for local tests."""
    return {
        "SLACK_BOT_TOKEN": "xoxb-test-token",
        "SLACK_SIGNING_SECRET": "test-signing-secret",
        "SLACK_BOT_USER_ID": "UBOT",
        "RAG_STATE_BACKEND": "memory",
    }


def test_configured_service_answers_a_slack_event_with_rag():
    """Deliver a semantic answer through the configured Slack boundary."""
    service = create_configured_slack_service(
        settings(),
        embeddings=FakeEmbeddings(),
        repository=FakeRepository(),
        state=InMemoryRagStateStore(),
        keyword_service=KnowledgeBaseService(MemoryRepository()),
    )
    client = MagicMock()
    event = {
        "type": "app_mention",
        "event_id": "Ev-rag-runtime",
        "channel": "C123",
        "user": "U123",
        "text": "<@UBOT> How do I get access?",
        "ts": "100.200",
    }

    reply = answer_slack_event(event, client, service)

    assert reply is not None
    assert reply.text == "Use the reviewed semantic answer."
    client.chat_postMessage.assert_called_once_with(
        channel="C123",
        text="Use the reviewed semantic answer.",
        thread_ts="100.200",
    )


def test_configured_service_uses_injected_notification_boundary():
    """Allow callers to inject notification behavior without Slack access."""
    notifier = RecordingNotifier()
    service = create_configured_slack_service(
        settings(),
        embeddings=FakeEmbeddings(),
        repository=FakeRepository(),
        state=InMemoryRagStateStore(),
        notifier=notifier,
    )

    response = service.knowledge_base.answer(
        "How do I get access?", user_id="U123", channel="C123"
    )

    assert isinstance(response, AnswerResponse)
    assert notifier.calls == []


def test_configured_app_requires_slack_credentials():
    """Reject an app configuration that omits required Slack credentials."""
    with pytest.raises(ValueError, match="SLACK_BOT_TOKEN"):
        create_configured_slack_app(
            {"RAG_STATE_BACKEND": "none"},
            embeddings=FakeEmbeddings(),
            repository=FakeRepository(),
        )


def test_configured_app_injects_credentials_without_network_calls():
    """Construct the Bolt app without validating a fake token remotely."""
    app = create_configured_slack_app(
        settings(),
        embeddings=FakeEmbeddings(),
        repository=FakeRepository(),
        state=InMemoryRagStateStore(),
        token_verification_enabled=False,
    )

    assert app.client.token == "xoxb-test-token"
