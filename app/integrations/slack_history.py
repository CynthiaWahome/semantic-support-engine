"""Rate-limit-safe Slack history access for the extraction pipeline."""

from __future__ import annotations

import http.client
import time
from collections.abc import Callable
from typing import Any, Protocol

from slack_sdk.errors import SlackApiError

RetrySleep = Callable[[float], None]


class SlackHistoryClient(Protocol):
    """Minimal Slack WebClient surface needed by the scraper."""

    def auth_test(self) -> Any:
        """Return the authenticated bot identity."""
        ...

    def conversations_list(self, **kwargs: Any) -> Any:
        """Return one page of visible channels."""
        ...

    def conversations_history(self, **kwargs: Any) -> Any:
        """Return one page of channel messages."""
        ...

    def conversations_replies(self, **kwargs: Any) -> Any:
        """Return one page of thread messages."""
        ...

    def conversations_members(self, **kwargs: Any) -> Any:
        """Return one page of channel members."""
        ...

    def users_info(self, **kwargs: Any) -> Any:
        """Return profile data for one user."""
        ...


def safe_api_call(
    function: Callable[..., Any],
    *args: Any,
    max_retries: int = 5,
    sleeper: RetrySleep = time.sleep,
    **kwargs: Any,
) -> Any:
    """Retry Slack rate limits and transient network failures."""
    if max_retries < 1:
        raise ValueError("max_retries must be positive")

    for attempt in range(max_retries):
        try:
            return function(*args, **kwargs)
        except SlackApiError as error:
            if error.response.get("error") != "ratelimited":
                raise
            headers = getattr(error.response, "headers", None)
            if headers is None:
                headers = error.response.get("headers", {})
            retry_after = int(headers.get("Retry-After", 5))
            wait = retry_after + 1
        except (http.client.IncompleteRead, OSError, TimeoutError):
            wait = 5 * (attempt + 1)

        if attempt < max_retries - 1:
            sleeper(wait)

    raise RuntimeError(f"Max retries ({max_retries}) exceeded on Slack API call")


class SlackHistoryReader:
    """Paginated Slack history adapter with no application-level policy."""

    def __init__(
        self,
        client: SlackHistoryClient,
        page_size: int = 200,
        sleeper: RetrySleep = time.sleep,
    ) -> None:
        """Configure a Slack client and the page-level retry delay."""
        if not 1 <= page_size <= 200:
            raise ValueError("page_size must be between 1 and 200")
        self.client = client
        self.page_size = page_size
        self.sleeper = sleeper

    def _call(self, function: Callable[..., Any], **kwargs: Any) -> Any:
        """Call one Slack method through the bounded retry wrapper."""
        return safe_api_call(function, **kwargs, sleeper=self.sleeper)

    def fetch_bot_user_id(self) -> str:
        """Resolve the bot ID used to exclude its own messages."""
        return str(self._call(self.client.auth_test)["user_id"])

    def list_channels(self) -> list[dict[str, Any]]:
        """List visible channels, retaining archived channels for filtering."""
        channels: list[dict[str, Any]] = []
        cursor: str | None = None
        seen_cursors: set[str] = set()
        while True:
            response = self._call(
                self.client.conversations_list,
                types="public_channel,private_channel",
                exclude_archived=False,
                limit=self.page_size,
                cursor=cursor,
            )
            channels.extend(response.get("channels", []))
            cursor = response.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                return channels
            if cursor in seen_cursors:
                raise RuntimeError("Slack pagination returned a repeated cursor")
            seen_cursors.add(cursor)
            self.sleeper(0.5)

    def fetch_channel_messages(self, channel_id: str) -> list[dict[str, Any]]:
        """Fetch every message in a channel."""
        messages: list[dict[str, Any]] = []
        cursor: str | None = None
        seen_cursors: set[str] = set()
        while True:
            response = self._call(
                self.client.conversations_history,
                channel=channel_id,
                limit=self.page_size,
                cursor=cursor,
            )
            messages.extend(response.get("messages", []))
            cursor = response.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                return messages
            if cursor in seen_cursors:
                raise RuntimeError("Slack pagination returned a repeated cursor")
            seen_cursors.add(cursor)
            self.sleeper(1.0)

    def fetch_thread_replies(
        self, channel_id: str, thread_ts: str
    ) -> list[dict[str, Any]]:
        """Fetch replies while excluding the root on every page."""
        replies: list[dict[str, Any]] = []
        cursor: str | None = None
        seen_cursors: set[str] = set()
        while True:
            response = self._call(
                self.client.conversations_replies,
                channel=channel_id,
                ts=thread_ts,
                limit=self.page_size,
                cursor=cursor,
            )
            replies.extend(
                message
                for message in response.get("messages", [])
                if message.get("ts") != thread_ts
            )
            cursor = response.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                return replies
            if cursor in seen_cursors:
                raise RuntimeError("Slack pagination returned a repeated cursor")
            seen_cursors.add(cursor)
            self.sleeper(0.5)

    def fetch_channel_members(self, channel_id: str) -> set[str]:
        """Fetch every member of a trusted-users channel."""
        members: set[str] = set()
        cursor: str | None = None
        seen_cursors: set[str] = set()
        while True:
            response = self._call(
                self.client.conversations_members,
                channel=channel_id,
                limit=self.page_size,
                cursor=cursor,
            )
            members.update(response.get("members", []))
            cursor = response.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                return members
            if cursor in seen_cursors:
                raise RuntimeError("Slack pagination returned a repeated cursor")
            seen_cursors.add(cursor)
            self.sleeper(0.5)

    def get_username(self, user_id: str) -> str:
        """Resolve a user ID to a display name."""
        profile = self._call(self.client.users_info, user=user_id)["user"]["profile"]
        return str(profile.get("display_name") or profile.get("real_name") or user_id)
