"""Behavior tests for Slack event handling and threaded answers."""

from unittest.mock import MagicMock

import pytest

from app.integrations.slack import answer_slack_event
from app.schemas.knowledge_base import AnswerResponse, KnowledgeTopic
from app.services.knowledge_base import KnowledgeBaseService
from app.services.slack_answering import (
    InMemoryDuplicateEventStore,
    SlackAnsweringService,
)


class MemoryRepository:
    def __init__(self) -> None:
        self.topics = {
            "access": KnowledgeTopic(
                keywords=["access"], answer="Use the account portal."
            )
        }

    def get_all_topics(self):
        return self.topics

    def set_all_topics(self, topics):
        self.topics = topics


def service(bot_user_id: str | None = "UBOT") -> SlackAnsweringService:
    return SlackAnsweringService(
        KnowledgeBaseService(MemoryRepository()),
        duplicate_events=InMemoryDuplicateEventStore(),
        bot_user_id=bot_user_id,
    )


class SemanticAnswerService:
    """Synthetic RAG composition proving Slack depends on the answer boundary."""

    def answer(self, question: str) -> AnswerResponse:
        """Return a semantic answer without exposing retrieval internals."""
        return AnswerResponse(
            answer="Semantic answer from the reviewed index.",
            source="semantic_retrieval",
        )


def semantic_service() -> SlackAnsweringService:
    """Compose Slack handling with the semantic answer implementation."""
    return SlackAnsweringService(
        SemanticAnswerService(),
        duplicate_events=InMemoryDuplicateEventStore(),
        bot_user_id="UBOT",
    )


def test_dm_is_answered_and_starts_a_thread():
    client = MagicMock()
    event = {
        "type": "message",
        "event_id": "Ev1",
        "channel": "D123",
        "channel_type": "im",
        "user": "U123",
        "text": "How do I get access?",
        "ts": "100.200",
    }

    reply = answer_slack_event(event, client, service())

    assert reply is not None
    client.chat_postMessage.assert_called_once_with(
        channel="D123", text="Use the account portal.", thread_ts="100.200"
    )


def test_slack_can_use_semantic_answer_service():
    """Deliver the RAG answer while preserving the Slack reply contract."""
    client = MagicMock()
    event = {
        "type": "app_mention",
        "event_id": "Ev-semantic",
        "channel": "C123",
        "user": "U123",
        "text": "<@UBOT> I cannot sign in",
        "ts": "150.200",
    }

    reply = answer_slack_event(event, client, semantic_service())

    assert reply is not None
    client.chat_postMessage.assert_called_once_with(
        channel="C123",
        text="Semantic answer from the reviewed index.",
        thread_ts="150.200",
    )


def test_mention_replies_in_the_existing_thread():
    client = MagicMock()
    event = {
        "type": "app_mention",
        "event_id": "Ev2",
        "channel": "C123",
        "user": "U123",
        "text": "<@UBOT> how do I get access?",
        "ts": "200.300",
        "thread_ts": "200.100",
    }

    answer_slack_event(event, client, service())

    client.chat_postMessage.assert_called_once_with(
        channel="C123", text="Use the account portal.", thread_ts="200.100"
    )


def test_mention_only_event_without_bot_id_is_ignored():
    client = MagicMock()
    event = {
        "type": "app_mention",
        "event_id": "Ev2-only",
        "channel": "C123",
        "user": "U123",
        "text": "<@UBOT>",
        "ts": "200.400",
    }

    assert answer_slack_event(event, client, service(bot_user_id=None)) is None
    client.chat_postMessage.assert_not_called()


def test_duplicate_event_is_not_posted_twice():
    client = MagicMock()
    answering = service()
    event = {
        "type": "app_mention",
        "event_id": "Ev3",
        "channel": "C123",
        "user": "U123",
        "text": "<@UBOT> access",
        "ts": "300.400",
    }

    answer_slack_event(event, client, answering)
    assert answer_slack_event(event, client, answering) is None
    client.chat_postMessage.assert_called_once()


def test_unmentioned_channel_message_is_ignored():
    client = MagicMock()
    event = {
        "type": "message",
        "event_id": "Ev4",
        "channel": "C123",
        "user": "U123",
        "text": "How do I get access?",
        "ts": "400.500",
    }

    assert answer_slack_event(event, client, service()) is None
    client.chat_postMessage.assert_not_called()


def test_bot_message_and_subtypes_are_ignored():
    client = MagicMock()
    answering = service()
    bot_event = {
        "type": "message",
        "event_id": "Ev5",
        "channel": "D123",
        "user": "UBOT",
        "text": "access",
        "ts": "500.600",
    }
    subtype_event = {
        "type": "message",
        "event_id": "Ev6",
        "channel": "D123",
        "user": "U123",
        "text": "access",
        "subtype": "message_changed",
        "ts": "600.700",
    }

    assert answer_slack_event(bot_event, client, answering) is None
    assert answer_slack_event(subtype_event, client, answering) is None
    client.chat_postMessage.assert_not_called()


def test_duplicate_store_expires_claims(monkeypatch):
    clock = iter([100.0, 100.1, 101.1])
    monkeypatch.setattr(
        "app.services.slack_answering.time.monotonic", lambda: next(clock)
    )
    store = InMemoryDuplicateEventStore(ttl_seconds=1)

    assert store.claim("Ev7")
    assert not store.claim("Ev7")
    assert store.claim("Ev7")


def test_failed_delivery_releases_event_claim():
    client = MagicMock()
    client.chat_postMessage.side_effect = [
        RuntimeError("temporary Slack failure"),
        None,
    ]
    answering = service()
    event = {
        "type": "app_mention",
        "event_id": "Ev8",
        "channel": "C123",
        "user": "U123",
        "text": "<@UBOT> access",
        "ts": "800.900",
    }

    with pytest.raises(RuntimeError, match="temporary Slack failure"):
        answer_slack_event(event, client, answering)

    assert answer_slack_event(event, client, answering) is not None
    assert client.chat_postMessage.call_count == 2


def test_failed_answer_releases_event_claim():
    client = MagicMock()
    answering = service()
    event = {
        "type": "app_mention",
        "event_id": "Ev9",
        "channel": "C123",
        "user": "U123",
        "text": "<@UBOT> access",
        "ts": "900.100",
    }
    answering.knowledge_base.answer = MagicMock(
        side_effect=[
            RuntimeError("temporary KB failure"),
            MagicMock(answer="Use the account portal."),
        ]
    )

    with pytest.raises(RuntimeError, match="temporary KB failure"):
        answering.answer_event(event)

    assert answering.answer_event(event) is not None
    client.chat_postMessage.assert_not_called()
