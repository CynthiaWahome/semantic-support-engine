"""Explicit local import: python -m app.sync_kb path/to/export.csv."""

import argparse
import os
from pathlib import Path

from app.core.knowledge_base import get_repository
from app.integrations.spreadsheet import CSVSpreadsheetReader, GoogleSheetsReader
from app.services.knowledge_base import KnowledgeBaseSyncService


def main() -> int:
    """Import the selected CSV, print its result, and signal failure with exit 1."""
    parser = argparse.ArgumentParser(description="Synchronize the knowledge base")
    parser.add_argument("csv", type=Path, nargs="?", help="local CSV export")
    parser.add_argument(
        "--google", action="store_true", help="read from configured Google Sheets"
    )
    args = parser.parse_args()
    if args.google == bool(args.csv):
        parser.error("provide a CSV path or use --google")
    if args.google:
        spreadsheet = GoogleSheetsReader.from_environment()
        configured_tabs = os.environ.get("GOOGLE_SHEET_TABS", "")
        tabs = [tab.strip() for tab in configured_tabs.split(",") if tab.strip()]
    else:
        spreadsheet = CSVSpreadsheetReader(args.csv)
        tabs = ()
    result = KnowledgeBaseSyncService(get_repository(), spreadsheet, tabs).sync()
    print(result.model_dump_json())
    return 0 if result.success else 1


if __name__ == "__main__":
    raise SystemExit(main())
