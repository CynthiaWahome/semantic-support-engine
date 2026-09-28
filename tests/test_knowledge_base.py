"""Carry over Thanos matcher regressions and exercise standalone boundaries."""

import json
import subprocess
import sys
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.core.knowledge_base import get_knowledge_base_service
from app.integrations.spreadsheet import CSVSpreadsheetReader, GoogleSheetsReader
from app.main import create_app
from app.repositories.knowledge_base import LocalKnowledgeBaseRepository
from app.schemas.knowledge_base import KnowledgeTopic
from app.services.knowledge_base import (
    KnowledgeBaseService,
    KnowledgeBaseSyncService,
    get_best_kb_match,
)


def topic(keyword="help", answer="Contact support", priority=0):
    return KnowledgeTopic(keywords=[keyword], answer=answer, priority=priority)


@pytest.mark.parametrize(
    ("keyword", "question", "expected"),
    [
        ("SUBMIT", "how do I submit?", "Answer"),
        ("valid", "invalid query", None),
        ("i am new", "Hello, i am new here", "Answer"),
        (":zero:", "What is :zero:?", "Answer"),
        ("c++", "Help with c++ please", "Answer"),
        ("help", "nothing relevant", None),
    ],
)
def test_matcher_preserves_original_word_and_phrase_behavior(
    keyword, question, expected
):
    assert get_best_kb_match(question, {"faq": topic(keyword, "Answer")}) == expected


def test_highest_priority_wins_including_negative_priorities():
    topics = {"low": topic(priority=-10), "high": topic(answer="High", priority=-2)}
    assert get_best_kb_match("help", topics) == "High"


def test_first_topic_wins_ties():
    assert get_best_kb_match(
        "help", {"first": topic(), "second": topic(answer="B")}
    ) == ("Contact support")


def test_periodic_topics_never_answer_questions():
    assert get_best_kb_match("help", {"periodic_update": topic(priority=100)}) is None
    assert get_best_kb_match("help", {}) is None


@pytest.fixture
def repository(tmp_path):
    return LocalKnowledgeBaseRepository(tmp_path / "data" / "topics.json")


def test_repository_round_trip_and_replace(repository):
    assert repository.get_all_topics() == {}
    assert not repository.path.exists()
    repository.set_all_topics({"faq": topic(answer="Résumé ✓")})
    assert repository.get_all_topics()["faq"].answer == "Résumé ✓"
    repository.set_all_topics({"replacement": topic()})
    assert list(repository.get_all_topics()) == ["replacement"]


@pytest.mark.parametrize("payload", ["broken json", "[]", '{"bad": {"answer": null}}'])
def test_corrupt_storage_falls_back_without_overwriting(tmp_path, payload):
    path = tmp_path / "topics.json"
    path.write_text(payload)
    service = KnowledgeBaseService(LocalKnowledgeBaseRepository(path))
    assert service.answer("help").source == "fallback"
    assert path.read_text() == payload


def test_failed_replace_preserves_previous_snapshot(repository, monkeypatch):
    repository.set_all_topics({"old": topic()})

    def fail_replace(*args):
        raise OSError("disk failure")

    monkeypatch.setattr("app.repositories.knowledge_base.os.replace", fail_replace)
    with pytest.raises(OSError):
        repository.set_all_topics({"new": topic()})
    assert list(repository.get_all_topics()) == ["old"]
    assert list(repository.path.parent.iterdir()) == [repository.path]


class FakeSheet:
    def __init__(self, tabs):
        self.tabs = tabs

    def get_tab_names(self):
        return list(self.tabs)

    def get_all(self, tab_name):
        rows = self.tabs[tab_name]
        if isinstance(rows, Exception):
            raise rows
        return rows


def row(**changes):
    return {"topic": "faq", "keywords": "help", "answer": "Answer", **changes}


def test_sync_normalizes_cells_and_skips_disabled_or_invalid_rows(repository):
    sheet = FakeSheet(
        {
            "Sheet1": [
                row(keywords=" HELP, Start Here, ,", priority="bad"),
                row(topic="disabled", enabled=False),
                row(topic="zero", enabled=0),
                row(topic="string", enabled="FALSE"),
                row(topic="empty", keywords=" , "),
                row(topic="no_answer", answer=" "),
                row(topic="periodic_notice", keywords="", priority="12"),
            ]
        }
    )
    result = KnowledgeBaseSyncService(repository, sheet).sync()
    assert result.success and result.topics_written == 2
    topics = repository.get_all_topics()
    assert set(topics) == {"faq", "periodic_notice"}
    assert topics["faq"].keywords == ["help", "start here"]
    assert topics["faq"].priority == 0
    assert topics["periodic_notice"].priority == 12


@pytest.mark.parametrize(
    "sheet,tabs",
    [
        (FakeSheet({"One": [row()], "Two": OSError("unavailable")}), ["One", "Two"]),
        (FakeSheet({"One": [row()]}), ["One", "Missing"]),
        (FakeSheet({"Other": [row()]}), []),
        (FakeSheet({"Sheet1": []}), []),
        (FakeSheet({"Sheet1": [row(answer="")]}), []),
    ],
)
def test_failed_sync_keeps_last_good_snapshot(repository, sheet, tabs):
    repository.set_all_topics({"old": topic()})
    result = KnowledgeBaseSyncService(repository, sheet, tabs).sync()
    assert not result.success and result.topics_written == 0
    assert list(repository.get_all_topics()) == ["old"]


def test_duplicate_topics_use_last_valid_row_and_tab(repository):
    sheet = FakeSheet({"One": [row(answer="First")], "Two": [row(answer="Last")]})
    result = KnowledgeBaseSyncService(repository, sheet, [" One ", "Two", "Two"]).sync()
    assert result.success and result.topics_written == 1
    assert repository.get_all_topics()["faq"].answer == "Last"


def test_all_disabled_rows_clear_old_answers(repository):
    repository.set_all_topics({"faq": topic()})
    sheet = FakeSheet({"Sheet1": [row(), row(enabled=False)]})
    result = KnowledgeBaseSyncService(repository, sheet).sync()
    assert result.success and result.topics_written == 0
    assert repository.get_all_topics() == {}


def test_tab_discovery_and_storage_failures_report_failure(repository, monkeypatch):
    repository.set_all_topics({"old": topic()})
    sheet = MagicMock()
    sheet.get_tab_names.side_effect = OSError("private provider details")
    assert not KnowledgeBaseSyncService(repository, sheet).sync().success

    def fail_write(*args):
        raise OSError("disk full")

    monkeypatch.setattr(repository, "set_all_topics", fail_write)
    assert (
        not KnowledgeBaseSyncService(repository, FakeSheet({"Sheet1": [row()]}))
        .sync()
        .success
    )
    assert list(repository.get_all_topics()) == ["old"]


def test_google_adapter_quotes_tab_names_and_maps_columns():
    service = MagicMock()
    spreadsheets = service.spreadsheets.return_value
    spreadsheets.get.return_value.execute.return_value = {
        "sheets": [{"properties": {"title": "Team's FAQ"}}]
    }
    values = spreadsheets.values.return_value
    values.get.return_value.execute.return_value = {"values": [["faq", "help", "A"]]}
    reader = GoogleSheetsReader(service, "test-sheet")
    assert reader.get_tab_names() == ["Team's FAQ"]
    assert reader.get_all("Team's FAQ") == [row(answer="A")]
    values.get.assert_called_once_with(
        spreadsheetId="test-sheet", range="'Team''s FAQ'!A2:E", majorDimension="ROWS"
    )


def test_csv_import_to_http_answer_and_fallback(tmp_path, repository):
    export = tmp_path / "faq.csv"
    export.write_text(
        "\ufeffTopic,Keywords,Answer,Enabled,Priority\n"
        'access,"login,sign in",Use the portal,TRUE,5\n',
        encoding="utf-8",
    )
    result = KnowledgeBaseSyncService(repository, CSVSpreadsheetReader(export)).sync()
    assert result.success
    app = create_app()
    app.dependency_overrides[get_knowledge_base_service] = lambda: KnowledgeBaseService(
        repository, fallback="Please ask the support team."
    )
    with TestClient(app) as client:
        match = client.post(
            "/knowledge-base/answer", json={"question": "How do I login?"}
        )
        assert match.status_code == 200
        assert match.json() == {"answer": "Use the portal", "source": "knowledge_base"}
        fallback = client.post("/knowledge-base/answer", json={"question": "unrelated"})
        assert fallback.json() == {
            "answer": "Please ask the support team.",
            "source": "fallback",
        }
        for body in [{}, {"question": " "}, {"question": "x" * 4001}]:
            assert client.post("/knowledge-base/answer", json=body).status_code == 422


@pytest.mark.parametrize(
    "csv",
    [
        "topic,answer\nfaq,A\n",
        "topic,keywords,answer,enabled,priority\nfaq,help,A,TRUE,0,extra\n",
    ],
)
def test_invalid_csv_preserves_storage(tmp_path, repository, csv):
    export = tmp_path / "faq.csv"
    export.write_text(csv)
    repository.set_all_topics({"old": topic()})
    assert (
        not KnowledgeBaseSyncService(repository, CSVSpreadsheetReader(export))
        .sync()
        .success
    )
    assert list(repository.get_all_topics()) == ["old"]


def test_cli_uses_configured_storage_and_failure_exit_code(tmp_path, monkeypatch):
    storage = tmp_path / "topics.json"
    export = tmp_path / "faq.csv"
    export.write_text("topic,keywords,answer,enabled,priority\nfaq,help,A,TRUE,0\n")
    monkeypatch.setenv("KB_STORAGE_PATH", str(storage))
    result = subprocess.run(
        [sys.executable, "-m", "app.sync_kb", str(export)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"success": True, "topics_written": 1}
    assert LocalKnowledgeBaseRepository(storage).get_all_topics()["faq"].answer == "A"
    result = subprocess.run(
        [sys.executable, "-m", "app.sync_kb", str(tmp_path / "missing.csv")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert json.loads(result.stdout) == {"success": False, "topics_written": 0}
