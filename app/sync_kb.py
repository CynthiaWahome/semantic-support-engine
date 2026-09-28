"""Explicit local import: python -m app.sync_kb path/to/export.csv."""

import argparse
from pathlib import Path

from app.core.knowledge_base import get_repository
from app.integrations.spreadsheet import CSVSpreadsheetReader
from app.services.knowledge_base import KnowledgeBaseSyncService


def main() -> int:
    """Import the selected CSV, print its result, and signal failure with exit 1."""
    parser = argparse.ArgumentParser(description="Import a knowledge-base CSV export")
    parser.add_argument("csv", type=Path)
    args = parser.parse_args()
    result = KnowledgeBaseSyncService(
        get_repository(), CSVSpreadsheetReader(args.csv)
    ).sync()
    print(result.model_dump_json())
    return 0 if result.success else 1


if __name__ == "__main__":
    raise SystemExit(main())
