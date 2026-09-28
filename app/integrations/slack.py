"""Slack transport adapter for the standalone answering service."""

from collections.abc import Mapping
from typing import Any, Protocol

from app.schemas.slack import SlackReply
from app.services.slack_answering import SlackAnsweringService


class SlackMessageClient(Protocol):
    """Minimal Slack client surface required by this feature."""

    def chat_postMessage(self, *, channel: str, text: str, thread_ts: str) -> Any:
        """Post a reply in an existing thread or start a new one."""
        ...


def answer_slack_event(
    event: Mapping[str, Any],
    client: SlackMessageClient,
    service: SlackAnsweringService,
) -> SlackReply | None:
    """Answer an event and deliver it through Slack when appropriate."""
    reply = service.answer_event(event)
    if reply is None:
        return None
    try:
        client.chat_postMessage(
            channel=reply.channel,
            text=reply.text,
            thread_ts=reply.thread_ts,
        )
    except Exception:
        service.release_event(event)
        raise
    return reply
