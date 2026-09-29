"""Atomic local persistence for extracted Slack Q&A records."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from app.schemas.scraper import ScrapedQAPair


class LocalDatasetRepository:
    """Store validated Q&A datasets as one replaceable JSON snapshot."""

    def __init__(self, path: Path) -> None:
        """Select the snapshot path without creating it."""
        self.path = path

    def load(self) -> list[ScrapedQAPair]:
        """Load a validated snapshot, returning an empty list if absent."""
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return []
        if not isinstance(payload, list):
            raise TypeError(f"Dataset snapshot must be a JSON list: {self.path}")
        return [ScrapedQAPair.model_validate(record) for record in payload]

    def save(self, records: list[ScrapedQAPair]) -> None:
        """Atomically replace the snapshot after validating every record."""
        validated = [ScrapedQAPair.model_validate(record) for record in records]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                dir=self.path.parent,
                prefix=f".{self.path.name}.",
                mode="w",
                encoding="utf-8",
                delete=False,
            ) as temporary:
                temporary_path = Path(temporary.name)
                json.dump(
                    [record.model_dump(mode="json") for record in validated],
                    temporary,
                    indent=2,
                    ensure_ascii=False,
                )
                temporary.write("\n")
                temporary.flush()
                os.fsync(temporary.fileno())
            os.replace(temporary_path, self.path)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
