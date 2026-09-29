"""Slack event and reply contracts used by the answering adapter."""

from dataclasses import dataclass


@dataclass(frozen=True)
class SlackReply:
    """A reply that can be sent through Slack's chat API."""

    channel: str
    text: str
    thread_ts: str


@dataclass(frozen=True)
class NormalizedSlackQuestion:
    """Validated question data extracted from one Slack event."""

    event_key: str
    channel: str
    user_id: str
    question: str
    thread_ts: str
