"""Policies, caching, rate limiting, and admin notification hooks for RAG."""

from __future__ import annotations

import hashlib
from typing import Any, Protocol

from app.core.rag_constants import (
    DEFAULT_BLOCKED_TOPICS,
    DEFAULT_CACHE_TTL_SECONDS,
    DEFAULT_RATE_LIMIT_PER_HOUR,
    DEFAULT_RATE_WINDOW_SECONDS,
)
from app.integrations.rag_state import RagStateStore

RATE_LIMIT_MESSAGE = (
    "You've sent a lot of questions in the last hour. "
    "Please review the pinned resources and try again later."
)


class RagAdminNotifier(Protocol):
    """Notification boundary for unanswered and rate-limited questions."""

    def notify(
        self,
        question: str,
        user_id: str,
        channel: str,
        reason: str,
    ) -> None:
        """Notify an administrator without changing the user response."""
        ...


class SlackRagAdminNotifier:
    """Send safe RAG notifications through an injected Slack client."""

    def __init__(self, client: Any, admin_channel: str) -> None:
        if not admin_channel.strip():
            raise ValueError("admin_channel must not be blank")
        self.client = client
        self.admin_channel = admin_channel

    def notify(
        self,
        question: str,
        user_id: str,
        channel: str,
        reason: str,
    ) -> None:
        """Post a bounded notification without logging or returning source data."""
        safe_question = _escape_slack_mrkdwn(question[:1000])
        self.client.chat_postMessage(
            channel=self.admin_channel,
            text=(
                f":question: *RAG {reason}*\n"
                f"*From:* <@{user_id}> in <#{channel}>\n"
                f"*Question:* {safe_question}"
            ),
        )


class RagSafeguards:
    """Apply the original RAG cache, rate, and blocked-topic policies."""

    def __init__(
        self,
        state: RagStateStore | None = None,
        *,
        cache_ttl_seconds: int = DEFAULT_CACHE_TTL_SECONDS,
        rate_limit_per_hour: int = DEFAULT_RATE_LIMIT_PER_HOUR,
        blocked_topics: tuple[str, ...] = DEFAULT_BLOCKED_TOPICS,
    ) -> None:
        if cache_ttl_seconds <= 0:
            raise ValueError("cache_ttl_seconds must be positive")
        if rate_limit_per_hour <= 0:
            raise ValueError("rate_limit_per_hour must be positive")
        self.state = state
        self.cache_ttl_seconds = cache_ttl_seconds
        self.rate_limit_per_hour = rate_limit_per_hour
        self.blocked_topics = tuple(topic.lower() for topic in blocked_topics)

    def is_blocked(self, question: str) -> bool:
        """Return true when a question contains a restricted topic."""
        normalized = question.lower()
        return any(topic in normalized for topic in self.blocked_topics)

    def get_cached(self, question: str) -> str | None:
        """Return a cached answer when a state store is configured."""
        if self.state is None:
            return None
        return self.state.get(self.cache_key(question))

    def cache(self, question: str, answer: str) -> None:
        """Cache one semantic answer when a state store is configured."""
        if self.state is not None:
            self.state.set(self.cache_key(question), answer, self.cache_ttl_seconds)

    def is_rate_limited(self, user_id: str, request_id: str = "") -> bool:
        """Return true after the limit, counting each request ID once."""
        if self.state is None or not user_id:
            return False
        key = f"rag:rate:{user_id}"
        if request_id:
            event_digest = hashlib.sha256(request_id.encode()).hexdigest()
            return self.state.increment_once(
                key,
                f"rag:rate:event:{event_digest}",
                DEFAULT_RATE_WINDOW_SECONDS,
                self.rate_limit_per_hour,
            )
        return (
            self.state.increment(key, DEFAULT_RATE_WINDOW_SECONDS)
            > self.rate_limit_per_hour
        )

    @staticmethod
    def cache_key(question: str) -> str:
        """Create a stable, non-sensitive cache key for normalized text."""
        digest = hashlib.sha256(question.lower().strip().encode()).hexdigest()
        return f"rag:cache:{digest}"


def _escape_slack_mrkdwn(value: str) -> str:
    """Escape Slack mrkdwn control characters in untrusted text."""
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
