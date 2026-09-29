"""Human- and machine-readable exports for curated Q&A candidates."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Sequence
from pathlib import Path

from openpyxl import Workbook
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE

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
EXCEL_CELL_MAX_LENGTH = 32_767


def _atomic_write(path: Path, content: str) -> None:
    """Replace a text file atomically so interrupted exports preserve the old file."""
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=path.parent,
            prefix=f".{path.name}.",
            mode="w",
            encoding="utf-8",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _safe_spreadsheet_value(field: str, value: object, record_id: str) -> object:
    """Make Slack-authored text safe and representable in an Excel cell."""
    if not isinstance(value, str):
        return value
    value = ILLEGAL_CHARACTERS_RE.sub("", value)
    if field == "answer" and len(value) > EXCEL_CELL_MAX_LENGTH:
        return f"[TRUNCATED: full answer in JSON record thread_ts={record_id}]"
    if value.startswith(("=", "+", "-", "@")):
        return f"'{value}"
    return value


def export_json(records: Sequence[ScrapedQAPair], path: Path) -> None:
    """Write records as UTF-8 JSON while retaining thread context."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [record.model_dump(mode="json") for record in records]
    _atomic_write(path, json.dumps(payload, indent=2, ensure_ascii=False) + "\n")


def export_xlsx(records: Sequence[ScrapedQAPair], path: Path) -> None:
    """Write scalar fields to an Excel review sheet."""
    path.parent.mkdir(parents=True, exist_ok=True)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Q&A review"
    sheet.append(list(EXPORT_FIELDS))
    for record in records:
        values = record.model_dump(mode="python")
        sheet.append(
            [
                _safe_spreadsheet_value(field, values[field], record.thread_ts)
                for field in EXPORT_FIELDS
            ]
        )
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions
    workbook.save(path)
