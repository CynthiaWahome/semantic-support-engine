"""Tests for Slack history extraction and answer scoring."""

from unittest.mock import MagicMock

import pytest
from slack_sdk.errors import SlackApiError

from app.integrations.slack_history import SlackHistoryReader, safe_api_call
from app.services.scraper import SlackQAScraper


class FakeReader:
    """In-memory history reader for scraper behavior tests."""

    def __init__(self):
        """Create predictable channel, message, and profile fixtures."""
        self.channels = [
            {"name": "support-general", "id": "C1", "is_member": True},
            {"name": "help-backend", "id": "C2", "is_member": True},
            {"name": "random", "id": "C3", "is_member": True},
            {"name": "support-archive", "id": "C4", "is_archived": True},
        ]
        self.messages = []
        self.replies = {}
        self.usernames = {"U_ASKER": "Asker", "U_MENTOR": "Mentor"}

    def list_channels(self):
        """Return configured channel fixtures."""
        return self.channels

    def fetch_channel_messages(self, channel_id):
        """Return configured message fixtures."""
        return self.messages

    def fetch_thread_replies(self, channel_id, thread_ts):
        """Return replies for the requested thread."""
        return self.replies[thread_ts]

    def fetch_channel_members(self, channel_id):
        """Return the fixture trusted-user set."""
        return {"U_MENTOR"}

    def get_username(self, user_id):
        """Resolve fixture user IDs to display names."""
        return self.usernames.get(user_id, user_id)


def test_channel_discovery_filters_patterns_membership_archive_and_exclusions():
    """Match configured prefixes while honoring exclusions."""
    scraper = SlackQAScraper(FakeReader(), channel_patterns=("support-",))

    assert scraper.discover_target_channels() == {
        "support-archive": "C4",
        "support-general": "C1",
    }
    assert scraper.discover_target_channels(excluded_channels=("support-archive",)) == {
        "support-general": "C1"
    }


def test_explicit_channels_are_not_pattern_limited():
    """Allow explicit accessible channels outside configured prefixes."""
    scraper = SlackQAScraper(FakeReader(), channel_patterns=("support-",))

    assert scraper.discover_target_channels(explicit_channels=("help-backend",)) == {
        "help-backend": "C2"
    }


def test_question_detection_avoids_broad_noise():
    """Reject vague status messages while accepting real questions."""
    assert SlackQAScraper.is_question("How do I deploy this?")
    assert SlackQAScraper.is_question("Has anyone seen this error")
    assert not SlackQAScraper.is_question("I am stuck")
    assert not SlackQAScraper.is_question("")


def test_process_channel_selects_mentor_answer_and_acceptance():
    """Combine mentor authorship, length, and asker acceptance signals."""
    reader = FakeReader()
    reader.messages = [
        {
            "user": "U_ASKER",
            "text": "How do I deploy this?",
            "ts": "1700000000.000000",
            "reply_count": 2,
        }
    ]
    reader.replies["1700000000.000000"] = [
        {
            "user": "U_MENTOR",
            "text": "Use the deployment guide and configure the production environment variables.",
            "ts": "1700000001.000000",
        },
        {
            "user": "U_ASKER",
            "text": "Thanks, that worked perfectly.",
            "ts": "1700000002.000000",
        },
    ]
    scraper = SlackQAScraper(reader, bot_user_id="U_BOT")
    scraper.load_mentor_ids({"experts": "C_MENTORS"})

    pairs = scraper.process_channel("support-general", "C1")

    assert len(pairs) == 1
    assert pairs[0].confidence_score == 1.0
    assert pairs[0].is_trusted_answer
    assert pairs[0].thread_ts == "1700000000.000000"
    assert pairs[0].answerer_name == "Mentor"


def test_process_channel_ignores_bot_subtypes_and_unanswered_threads():
    """Exclude bot messages, subtypes, and threads without replies."""
    reader = FakeReader()
    reader.messages = [
        {"user": "U_BOT", "text": "How?", "ts": "1", "reply_count": 1},
        {
            "user": "U_ASKER",
            "text": "How do I sign in?",
            "ts": "2",
            "reply_count": 1,
            "subtype": "bot_message",
        },
        {"user": "U_ASKER", "text": "How do I sign in?", "ts": "3", "reply_count": 0},
    ]
    scraper = SlackQAScraper(reader, bot_user_id="U_BOT")

    assert scraper.process_channel("support-general", "C1") == []


def test_safe_api_call_retries_rate_limits():
    """Retry a rate-limited call using Slack's retry-after value."""
    function = MagicMock(
        side_effect=[
            SlackApiError(
                message="rate limited",
                response={"error": "ratelimited", "headers": {"Retry-After": "2"}},
            ),
            "ok",
        ]
    )
    waits = []

    assert safe_api_call(function, sleeper=waits.append) == "ok"
    assert waits == [3]


def test_history_reader_excludes_thread_root_on_every_page():
    """Remove the root message even when it appears on later pages."""
    client = MagicMock()
    client.conversations_replies.side_effect = [
        {
            "messages": [{"ts": "1"}, {"ts": "1.1"}],
            "response_metadata": {"next_cursor": "next"},
        },
        {"messages": [{"ts": "1"}, {"ts": "1.2"}]},
    ]
    reader = SlackHistoryReader(client, page_size=2, sleeper=lambda _: None)

    assert reader.fetch_thread_replies("C1", "1") == [{"ts": "1.1"}, {"ts": "1.2"}]
    assert client.conversations_replies.call_count == 2


@pytest.mark.parametrize(
    "method_name,method_call",
    [
        ("conversations_list", lambda reader: reader.list_channels()),
        (
            "conversations_history",
            lambda reader: reader.fetch_channel_messages("C1"),
        ),
        (
            "conversations_replies",
            lambda reader: reader.fetch_thread_replies("C1", "1"),
        ),
        (
            "conversations_members",
            lambda reader: reader.fetch_channel_members("C1"),
        ),
    ],
)
def test_history_reader_rejects_repeated_cursors(method_name, method_call):
    """Stop every pagination loop when Slack repeats a cursor."""
    client = MagicMock()
    client_method = getattr(client, method_name)
    client_method.return_value = {
        "channels": [],
        "messages": [],
        "members": [],
        "response_metadata": {"next_cursor": "stuck"},
    }
    reader = SlackHistoryReader(client, sleeper=lambda _: None)

    with pytest.raises(RuntimeError, match="repeated cursor"):
        method_call(reader)


def test_failed_mentor_refresh_clears_previous_trusted_users():
    """Do not reuse stale mentor labels after a refresh failure."""
    reader = FakeReader()
    reader.fetch_channel_members = MagicMock(side_effect=RuntimeError("unavailable"))
    scraper = SlackQAScraper(reader)
    scraper.mentor_ids = {"U_OLD_MENTOR"}

    with pytest.raises(RuntimeError, match="unavailable"):
        scraper.load_mentor_ids({"experts": "C_MENTORS"})

    assert scraper.mentor_ids == set()
