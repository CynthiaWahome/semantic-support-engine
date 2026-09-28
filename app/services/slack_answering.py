"""Slack-independent answering and duplicate-event protection."""

import re
import time
from collections.abc import Mapping
from threading import Lock
from typing import Any, Protocol

from app.schemas.slack import NormalizedSlackQuestion, SlackReply
from app.services.knowledge_base import KnowledgeBaseService


class DuplicateEventStore(Protocol):
    """Storage boundary for event keys that have already been claimed."""

    def claim(self, key: str) -> bool:
        """Return true only when this key has not been claimed recently."""
        ...

    def release(self, key: str) -> None:
        """Remove a claim when delivery fails before Slack accepts the reply."""
        ...


class InMemoryDuplicateEventStore:
    """Process-local TTL store for development and single-worker deployments."""

    def __init__(self, ttl_seconds: float = 600.0) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        self.ttl_seconds = ttl_seconds
        self._expires_at: dict[str, float] = {}
        self._lock = Lock()

    def claim(self, key: str) -> bool:
        """Atomically claim a key until its TTL expires."""
        now = time.monotonic()
        with self._lock:
            self._expires_at = {
                stored_key: expires_at
                for stored_key, expires_at in self._expires_at.items()
                if expires_at > now
            }
            if key in self._expires_at:
                return False
            self._expires_at[key] = now + self.ttl_seconds
            return True

    def release(self, key: str) -> None:
        """Release a claim so a failed delivery can be retried."""
        with self._lock:
            self._expires_at.pop(key, None)


def _strip_mention(text: str, bot_user_id: str | None) -> str:
    """Remove the bot's Slack mention from a question."""
    if not bot_user_id:
        return re.sub(r"^<@[^>]+>\s*", "", text, count=1).strip()
    return text.replace(f"<@{bot_user_id}>", " ").strip()


def _event_key(event: Mapping[str, Any]) -> str:
    """Prefer Slack's stable event ID and provide a deterministic fallback."""
    event_id = str(event.get("event_id", "")).strip()
    if event_id:
        return f"event:{event_id}"
    return "message:" + "|".join(
        str(event.get(field, "")) for field in ("channel", "ts", "user", "text")
    )


def _normalize_question(
    event: Mapping[str, Any], bot_user_id: str | None
) -> NormalizedSlackQuestion | None:
    """Accept direct messages and mentions while ignoring unsupported events."""
    event_type = str(event.get("type", "message"))
    if event.get("subtype") or event_type not in {"message", "app_mention"}:
        return None

    channel = str(event.get("channel", "")).strip()
    user = str(event.get("user", "")).strip()
    message_ts = str(event.get("ts", "")).strip()
    text = str(event.get("text", "")).strip()
    if not channel or not user or not message_ts or not text:
        return None
    if bot_user_id and user == bot_user_id:
        return None

    is_direct_message = event.get("channel_type") == "im" or channel.startswith("D")
    has_mention = event_type == "app_mention" or (
        bot_user_id is not None and f"<@{bot_user_id}>" in text
    )
    if not is_direct_message and not has_mention:
        return None

    question = _strip_mention(text, bot_user_id)
    if not question:
        return None
    return NormalizedSlackQuestion(
        event_key=_event_key(event),
        channel=channel,
        question=question,
        thread_ts=str(event.get("thread_ts") or message_ts),
    )


class SlackAnsweringService:
    """Turn supported Slack events into threaded replies."""

    def __init__(
        self,
        knowledge_base: KnowledgeBaseService,
        duplicate_events: DuplicateEventStore | None = None,
        bot_user_id: str | None = None,
    ) -> None:
        self.knowledge_base = knowledge_base
        self.duplicate_events = duplicate_events or InMemoryDuplicateEventStore()
        self.bot_user_id = bot_user_id

    def answer_event(self, event: Mapping[str, Any]) -> SlackReply | None:
        """Return one answer for a new supported event, or no reply."""
        question = _normalize_question(event, self.bot_user_id)
        if question is None or not self.duplicate_events.claim(question.event_key):
            return None
        try:
            answer = self.knowledge_base.answer(question.question)
        except Exception:
            self.duplicate_events.release(question.event_key)
            raise
        return SlackReply(
            channel=question.channel,
            text=answer.answer,
            thread_ts=question.thread_ts,
        )

    def release_event(self, event: Mapping[str, Any]) -> None:
        """Release the event claim after a failed Slack delivery."""
        question = _normalize_question(event, self.bot_user_id)
        if question is not None:
            self.duplicate_events.release(question.event_key)
