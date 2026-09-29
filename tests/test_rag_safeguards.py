"""Tests for RAG cache, rate, policy, and notification safeguards."""

from unittest.mock import MagicMock, patch

from app.integrations.rag_state import InMemoryRagStateStore, UpstashRagStateStore
from app.schemas.knowledge_base import KnowledgeTopic
from app.schemas.retrieval import RetrievalDocument, RetrievedDocument
from app.services.knowledge_base import KnowledgeBaseService
from app.services.rag_safeguards import (
    RATE_LIMIT_MESSAGE,
    RagSafeguards,
    SlackRagAdminNotifier,
)
from app.services.retrieval import RagKnowledgeBaseService


class MemoryRepository:
    """Minimal keyword repository for fallback behavior."""

    def get_all_topics(self):
        return {
            "access": KnowledgeTopic(
                keywords=["access"], answer="Use the account portal."
            )
        }

    def set_all_topics(self, topics):
        raise NotImplementedError


class FakeRetrieval:
    """Retrieval double with controllable matches and call tracking."""

    def __init__(self, matches=()):
        self.matches = list(matches)
        self.calls = 0

    def retrieve(self, question: str):
        self.calls += 1
        return self.matches


class RecordingNotifier:
    """Notifier double that records policy events without Slack."""

    def __init__(self):
        self.calls = []

    def notify(self, question, user_id, channel, reason):
        self.calls.append((question, user_id, channel, reason))


def semantic_match(answer: str = "Use the reviewed portal."):
    """Build one confident retrieval result."""
    return [
        RetrievedDocument(
            document=RetrievalDocument(
                document_id="thread-1",
                question="How do I access my account?",
                answer=answer,
                source="support-general",
            ),
            score=0.91,
        )
    ]


def rag(retrieval, safeguards=None, notifier=None):
    """Compose the safeguards-aware service with the keyword fallback."""
    return RagKnowledgeBaseService(
        retrieval,
        KnowledgeBaseService(MemoryRepository()),
        safeguards=safeguards,
        notifier=notifier,
    )


def test_semantic_answer_is_cached_and_reused():
    """Cache a semantic answer and avoid a second retrieval call."""
    retrieval = FakeRetrieval(semantic_match())
    safeguards = RagSafeguards(InMemoryRagStateStore())
    service = rag(retrieval, safeguards)

    first = service.answer("How do I access my account?", user_id="U1")
    second = service.answer("How do I access my account?", user_id="U1")

    assert first.answer == second.answer == "Use the reviewed portal."
    assert second.source == "semantic_retrieval"
    assert retrieval.calls == 1


def test_rate_limit_returns_safe_message_and_notifies():
    """Stop requests after the configured hourly limit."""
    retrieval = FakeRetrieval(semantic_match())
    safeguards = RagSafeguards(InMemoryRagStateStore(), rate_limit_per_hour=1)
    notifier = RecordingNotifier()
    service = rag(retrieval, safeguards, notifier)

    service.answer("first", user_id="U1", channel="C1")
    response = service.answer("second", user_id="U1", channel="C1")

    assert response.answer == RATE_LIMIT_MESSAGE
    assert notifier.calls[-1][-1] == "rate limited"


def test_blocked_topic_cannot_bypass_policy_through_keyword_fallback():
    """Return generic fallback instead of exposing a restricted keyword answer."""
    keyword = MagicMock(
        fallback="Please ask support.",
        answer=MagicMock(),
    )
    service = RagKnowledgeBaseService(
        FakeRetrieval(),
        keyword,
        safeguards=RagSafeguards(InMemoryRagStateStore()),
    )

    response = service.answer("What are the promotion criteria?", user_id="U1")

    assert response.answer == "Please ask support."
    keyword.answer.assert_not_called()


def test_unanswered_question_notifies_then_uses_keyword_fallback():
    """Notify administrators without changing the existing fallback answer."""
    notifier = RecordingNotifier()
    service = rag(FakeRetrieval(), RagSafeguards(), notifier)

    response = service.answer("How do I get access?", user_id="U1", channel="C1")

    assert response.answer == "Use the account portal."
    assert notifier.calls == [
        ("How do I get access?", "U1", "C1", "unanswered question")
    ]


def test_safeguarded_answer_requires_user_identity():
    """Prevent callers from bypassing rate limiting with an empty identity."""
    service = rag(FakeRetrieval(), RagSafeguards(InMemoryRagStateStore()))

    try:
        service.answer("How do I get access?")
    except ValueError as error:
        assert str(error) == "user_id is required when RAG safeguards are enabled"
    else:
        raise AssertionError("expected safeguarded answers to require user_id")


def test_upstash_adapter_maps_state_operations():
    """Translate the minimal state interface to the Upstash client methods."""
    client = MagicMock()
    client.get.return_value = "cached"
    client.eval.return_value = 1
    store = UpstashRagStateStore(client)

    assert store.get("key") == "cached"
    store.set("key", "value", 60)
    assert store.increment("rate", 3600) == 1

    client.set.assert_called_once_with("key", "value", ex=60)
    client.eval.assert_called_once()


def test_in_memory_rate_window_is_not_extended_by_retries():
    """Keep the first request's expiry for the whole rate-limit window."""
    store = InMemoryRagStateStore()

    with patch(
        "app.integrations.rag_state.time.monotonic",
        side_effect=[100.0, 100.5, 101.1],
    ):
        assert store.increment("rate", 1) == 1
        assert store.increment("rate", 1) == 2
        assert store.increment("rate", 1) == 1


def test_slack_admin_notifier_formats_bounded_notification():
    """Send unanswered questions through the injected Slack client."""
    client = MagicMock()
    notifier = SlackRagAdminNotifier(client, "U_ADMIN")

    notifier.notify("question", "U1", "C1", "unanswered question")

    client.chat_postMessage.assert_called_once_with(
        channel="U_ADMIN",
        text=(
            ":question: *RAG unanswered question*\n"
            "*From:* <@U1> in <#C1>\n"
            "*Question:* question"
        ),
    )


def test_slack_admin_notifier_escapes_untrusted_mrkdwn():
    """Prevent user text from triggering Slack control syntax."""
    client = MagicMock()
    notifier = SlackRagAdminNotifier(client, "U_ADMIN")

    notifier.notify("& <!channel> <tag>", "U1", "C1", "unanswered question")

    text = client.chat_postMessage.call_args.kwargs["text"]
    assert "&amp; &lt;!channel&gt; &lt;tag&gt;" in text
