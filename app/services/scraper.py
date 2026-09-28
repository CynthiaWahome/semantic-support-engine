"""Extract high-signal Q&A pairs from Slack conversation history."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any, Protocol

from app.schemas.scraper import ScrapedQAPair, ThreadContextMessage

DEFAULT_ACCEPTANCE_SIGNALS = (
    "thank",
    "thanks",
    "solved",
    "got it",
    "perfect",
    "works",
    "worked",
    "awesome",
    "great",
    "okay thanks",
    "ok thanks",
    "that helped",
    "makes sense",
    "understood",
    "appreciate",
    "cheers",
    "sorted",
    "fixed",
)
DEFAULT_QUESTION_STARTERS = (
    "how do",
    "how can",
    "how should",
    "how would",
    "how does",
    "what is",
    "what are",
    "what does",
    "what should",
    "what's",
    "why is",
    "why does",
    "why can't",
    "why won't",
    "when is",
    "when does",
    "when should",
    "where is",
    "where do",
    "where can",
    "who is",
    "who can",
    "who should",
    "which is",
    "which should",
    "can i",
    "can you",
    "could i",
    "could you",
    "should i",
    "should we",
    "is it",
    "is there",
    "is this",
    "do i",
    "do we",
    "does it",
    "am i",
    "will it",
    "would it",
    "has anyone",
)


class HistoryReader(Protocol):
    """Reader boundary allowing the service to run without Slack."""

    def list_channels(self) -> list[dict[str, Any]]:
        """Return channel metadata visible to the reader."""
        ...

    def fetch_channel_messages(self, channel_id: str) -> list[dict[str, Any]]:
        """Return all messages for one channel."""
        ...

    def fetch_thread_replies(
        self, channel_id: str, thread_ts: str
    ) -> list[dict[str, Any]]:
        """Return replies for one thread without its root message."""
        ...

    def fetch_channel_members(self, channel_id: str) -> set[str]:
        """Return user IDs in one trusted-users channel."""
        ...

    def get_username(self, user_id: str) -> str:
        """Return a display name for one Slack user ID."""
        ...


class SlackQAScraper:
    """Policy layer for turning Slack history into reviewed candidates."""

    def __init__(
        self,
        reader: HistoryReader,
        *,
        channel_patterns: Sequence[str] = ("support-", "help-"),
        mentors_channel: str = "experts",
        min_answer_length: int = 30,
        bot_user_id: str | None = None,
    ) -> None:
        """Configure channel policy, scoring thresholds, and bot exclusion."""
        if min_answer_length < 1:
            raise ValueError("min_answer_length must be positive")
        self.reader = reader
        self.channel_patterns = tuple(p.strip() for p in channel_patterns if p.strip())
        self.mentors_channel = mentors_channel
        self.min_answer_length = min_answer_length
        self.bot_user_id = bot_user_id
        self.mentor_ids: set[str] = set()
        self._user_cache: dict[str, str] = {}

    def discover_target_channels(
        self,
        explicit_channels: Sequence[str] | None = None,
        excluded_channels: Sequence[str] = (),
    ) -> dict[str, str]:
        """Return accessible matching channel names and IDs."""
        channels = {
            str(channel["name"]): str(channel["id"])
            for channel in self.reader.list_channels()
            if channel.get("is_member") or channel.get("is_archived")
        }
        excluded = set(excluded_channels)
        if explicit_channels:
            return {
                name: channels[name]
                for name in explicit_channels
                if name in channels and name not in excluded
            }
        return {
            name: channel_id
            for name, channel_id in sorted(channels.items())
            if name not in excluded
            and any(name.startswith(pattern) for pattern in self.channel_patterns)
        }

    def load_mentor_ids(self, channels: dict[str, str]) -> set[str]:
        """Load trusted answerers when the configured channel is accessible."""
        channel_id = channels.get(self.mentors_channel)
        self.mentor_ids = set()
        if channel_id:
            self.mentor_ids = self.reader.fetch_channel_members(channel_id)
        return self.mentor_ids

    @staticmethod
    def is_question(text: str) -> bool:
        """Accept explicit questions and known question-opening phrases."""
        normalised = text.strip().lower()
        return bool(normalised) and (
            "?" in normalised
            or any(
                normalised.startswith(starter) for starter in DEFAULT_QUESTION_STARTERS
            )
        )

    def score_answer(
        self,
        answerer_id: str,
        answer_text: str,
        subsequent_messages: Sequence[dict[str, Any]],
        question_asker_id: str,
    ) -> float:
        """Score mentor authorship, useful length, and asker acceptance."""
        score = 0.5 if answerer_id in self.mentor_ids else 0.0
        if len(answer_text) >= self.min_answer_length:
            score += 0.2
        if any(
            message.get("user") == question_asker_id
            and any(
                signal in str(message.get("text", "")).lower()
                for signal in DEFAULT_ACCEPTANCE_SIGNALS
            )
            for message in subsequent_messages
        ):
            score += 0.3
        return min(score, 1.0)

    def _username(self, user_id: str) -> str:
        """Resolve and cache a display name for one user ID."""
        if user_id not in self._user_cache:
            self._user_cache[user_id] = self.reader.get_username(user_id)
        return self._user_cache[user_id]

    def extract_best_answer(
        self,
        channel_name: str,
        question_text: str,
        thread_ts: str,
        asker_id: str,
        replies: Sequence[dict[str, Any]],
    ) -> ScrapedQAPair | None:
        """Return one strongest qualifying answer for a thread."""
        best: ScrapedQAPair | None = None
        best_score = -1.0
        for index, reply in enumerate(replies):
            answerer_id = reply.get("user")
            answer_text = str(reply.get("text", ""))
            if (
                not answerer_id
                or len(answer_text) < self.min_answer_length
                or answerer_id in {asker_id, self.bot_user_id}
            ):
                continue
            score = self.score_answer(
                str(answerer_id), answer_text, replies[index + 1 :], asker_id
            )
            if score <= best_score:
                continue
            context = [
                ThreadContextMessage(
                    author=self._username(str(message.get("user", "unknown"))),
                    text=str(message.get("text", "")),
                    is_mentor=message.get("user") in self.mentor_ids,
                )
                for message in replies
            ]
            best_score = score
            best = ScrapedQAPair(
                question=question_text,
                answer=answer_text,
                confidence_score=round(score, 2),
                is_trusted_answer=str(answerer_id) in self.mentor_ids,
                source_channel=channel_name,
                thread_ts=thread_ts,
                asker_name=self._username(asker_id),
                answerer_name=self._username(str(answerer_id)),
                date=datetime.fromtimestamp(float(thread_ts), tz=UTC)
                .date()
                .isoformat(),
                full_thread_context=context,
            )
        return best

    def process_channel(
        self, channel_name: str, channel_id: str
    ) -> list[ScrapedQAPair]:
        """Extract candidates from every qualifying thread in one channel."""
        pairs: list[ScrapedQAPair] = []
        for message in self.reader.fetch_channel_messages(channel_id):
            if message.get("subtype") or not message.get("user"):
                continue
            if message.get("user") == self.bot_user_id or not message.get(
                "reply_count", 0
            ):
                continue
            question = str(message.get("text", ""))
            if not self.is_question(question):
                continue
            thread_ts = str(message.get("thread_ts") or message.get("ts", ""))
            if not thread_ts:
                continue
            replies = self.reader.fetch_thread_replies(channel_id, thread_ts)
            pair = self.extract_best_answer(
                channel_name, question, thread_ts, str(message["user"]), replies
            )
            if pair is not None:
                pairs.append(pair)
        return pairs
