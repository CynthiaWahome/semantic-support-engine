"""Human- and machine-readable exports for curated Q&A candidates."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

from openpyxl import Workbook

from app.schemas.scraper import ScrapedQAPair

EXPORT_FIELDS = (
    "question",
    "answer",
    "confidence_score",
    "is_trusted_answer",
    "source_channel",
    "thread_ts",
    "asker_name",
    "answerer_name",
    "date",
)


def export_json(records: Sequence[ScrapedQAPair], path: Path) -> None:
    """Write records as UTF-8 JSON while retaining thread context."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [record.model_dump(mode="json") for record in records]
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def export_xlsx(records: Sequence[ScrapedQAPair], path: Path) -> None:
    """Write scalar fields to an Excel review sheet."""
    path.parent.mkdir(parents=True, exist_ok=True)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Q&A review"
    sheet.append(list(EXPORT_FIELDS))
    for record in records:
        values = record.model_dump(mode="python")
        sheet.append([values[field] for field in EXPORT_FIELDS])
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions
    workbook.save(path)
