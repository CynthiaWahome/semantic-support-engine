"""Application service for sorting, checkpointing, and exporting datasets."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from app.integrations.dataset_export import export_json, export_xlsx
from app.repositories.dataset import LocalDatasetRepository
from app.schemas.scraper import ScrapedQAPair


class DatasetService:
    """Publish extracted records as checkpoints and reviewable snapshots."""

    def __init__(self, repository: LocalDatasetRepository) -> None:
        """Use the supplied local dataset repository."""
        self.repository = repository

    @staticmethod
    def sort_records(records: Sequence[ScrapedQAPair]) -> list[ScrapedQAPair]:
        """Sort strongest candidates first without mutating the input."""
        return sorted(records, key=lambda record: record.confidence_score, reverse=True)

    def checkpoint(self, records: Sequence[ScrapedQAPair], path: Path) -> None:
        """Persist the current extraction progress as a validated JSON file."""
        LocalDatasetRepository(path).save(list(records))

    def publish(
        self,
        records: Sequence[ScrapedQAPair],
        json_path: Path,
        xlsx_path: Path | None = None,
    ) -> list[ScrapedQAPair]:
        """Sort and publish the final JSON and optional Excel snapshots."""
        sorted_records = self.sort_records(records)
        self.repository.save(sorted_records)
        export_json(sorted_records, json_path)
        if xlsx_path is not None:
            export_xlsx(sorted_records, xlsx_path)
        return sorted_records
