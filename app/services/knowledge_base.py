"""Thanos keyword matching and spreadsheet sync, decoupled from Slack/config."""

import logging
import re
from collections.abc import Sequence
from typing import Any

from app.integrations.spreadsheet import SpreadsheetReader
from app.repositories.knowledge_base import KnowledgeBaseRepository, Topics
from app.schemas.knowledge_base import AnswerResponse, KnowledgeTopic, SyncResult

logger = logging.getLogger(__name__)
DEFAULT_FALLBACK = (
    "I couldn't find an answer in the knowledge base. Please ask support."
)


def get_best_kb_match(text: str, kb: Topics) -> str | None:
    """Whole-word/phrase matching; highest priority wins, first wins ties."""
    normalised = text.lower()
    best: KnowledgeTopic | None = None
    for topic, data in kb.items():
        if topic.startswith("periodic_"):
            continue
        for keyword in data.keywords:
            pattern = rf"(?<!\w){re.escape(keyword.strip().lower())}(?!\w)"
            if re.search(pattern, normalised):
                # Unlike the old -1 sentinel, negative priorities also work.
                if best is None or data.priority > best.priority:
                    best = data
                break
    return best.answer if best is not None else None


class KnowledgeBaseService:
    def __init__(
        self, repository: KnowledgeBaseRepository, fallback: str = DEFAULT_FALLBACK
    ):
        self.repository = repository
        self.fallback = fallback

    def answer(self, question: str) -> AnswerResponse:
        match = get_best_kb_match(question, self.repository.get_all_topics())
        return AnswerResponse(
            answer=match if match is not None else self.fallback,
            source="knowledge_base" if match is not None else "fallback",
        )


def _cell(row: dict[str, Any], key: str) -> str:
    value = row.get(key)
    return "" if value is None else str(value).strip()


class KnowledgeBaseSyncService:
    def __init__(
        self,
        repository: KnowledgeBaseRepository,
        spreadsheet: SpreadsheetReader,
        tabs: Sequence[str] = (),
    ):
        self.repository = repository
        self.spreadsheet = spreadsheet
        self.tabs = list(dict.fromkeys(tab.strip() for tab in tabs if tab.strip()))

    def sync(self) -> SyncResult:
        """Replace the snapshot only after all tabs are read successfully.

        Missing requested tabs fail closed. With no selection, use Sheet1.
        Preserve the previous snapshot on empty/fully rejected input. Explicitly
        disabling every topic is a valid replacement with an empty snapshot.
        """
        try:
            available = self.spreadsheet.get_tab_names()
            tabs = self.tabs or ["Sheet1"]
            if any(tab not in available for tab in tabs):
                return SyncResult(success=False)
            combined: Topics = {}
            accepted_rows = 0
            for tab in tabs:
                for row in self.spreadsheet.get_all(tab):
                    topic = _cell(row, "topic")
                    answer = _cell(row, "answer")
                    enabled = (_cell(row, "enabled") or "true").lower()
                    if topic and enabled in {"false", "0", "no", "n"}:
                        accepted_rows += 1
                        combined.pop(topic, None)
                        continue
                    if (
                        not topic
                        or not answer
                        or enabled not in {"true", "1", "yes", "y"}
                    ):
                        continue
                    keywords = [
                        word.strip().lower()
                        for word in _cell(row, "keywords").split(",")
                        if word.strip()
                    ]
                    if not keywords and not topic.startswith("periodic_"):
                        continue
                    try:
                        priority = int(_cell(row, "priority") or 0)
                    except ValueError:
                        priority = 0
                    # Preserve the original later-row/tab-wins duplicate rule.
                    combined[topic] = KnowledgeTopic(
                        keywords=keywords, answer=answer, priority=priority
                    )
                    accepted_rows += 1
            if not accepted_rows:
                return SyncResult(success=False)
            self.repository.set_all_topics(combined)
            return SyncResult(success=True, topics_written=len(combined))
        except Exception:  # noqa: BLE001 — injected providers have unrelated error types
            # Provider error strings can expose source content or credentials.
            logger.warning("Knowledge-base sync failed; previous snapshot retained")
            return SyncResult(success=False)
