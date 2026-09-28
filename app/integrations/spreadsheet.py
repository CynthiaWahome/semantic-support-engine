"""Read-only spreadsheet adapters; authentication is owned by the caller."""

import csv
from pathlib import Path
from typing import Any, Protocol

COLUMNS = ("topic", "keywords", "answer", "enabled", "priority")


class SpreadsheetReader(Protocol):
    def get_tab_names(self) -> list[str]: ...

    def get_all(self, tab_name: str) -> list[dict[str, Any]]: ...


class GoogleSheetsReader:
    """Accept a pre-authenticated Google Sheets v4 discovery service.

    Only read methods are used. Provision the client with the
    spreadsheets.readonly scope outside this adapter; no credential files are read.
    Columns A:E follow the original Thanos layout; row 1 is a header.
    """

    def __init__(self, service: Any, spreadsheet_id: str):
        if not spreadsheet_id.strip():
            raise ValueError("Spreadsheet ID is required")
        self.service = service
        self.spreadsheet_id = spreadsheet_id

    def get_tab_names(self) -> list[str]:
        document = (
            self.service.spreadsheets()
            .get(spreadsheetId=self.spreadsheet_id, fields="sheets.properties.title")
            .execute()
        )
        return [sheet["properties"]["title"] for sheet in document.get("sheets", [])]

    def get_all(self, tab_name: str) -> list[dict[str, Any]]:
        escaped = tab_name.replace("'", "''")
        document = (
            self.service.spreadsheets()
            .values()
            .get(
                spreadsheetId=self.spreadsheet_id,
                range=f"'{escaped}'!A2:E",
                majorDimension="ROWS",
            )
            .execute()
        )
        return [dict(zip(COLUMNS, row)) for row in document.get("values", [])]


class CSVSpreadsheetReader:
    """Read one UTF-8 CSV exported from Excel or Google Sheets as Sheet1."""

    def __init__(self, path: Path):
        self.path = path

    def get_tab_names(self) -> list[str]:
        return ["Sheet1"]

    def get_all(self, tab_name: str) -> list[dict[str, Any]]:
        if tab_name != "Sheet1":
            raise ValueError("CSV exports contain a single tab: Sheet1")
        with self.path.open(encoding="utf-8-sig", newline="") as source:
            reader = csv.DictReader(source)
            headers = [name.strip().lower() for name in reader.fieldnames or []]
            if len(set(headers)) != len(headers) or set(headers) != set(COLUMNS):
                raise ValueError("CSV must contain the five knowledge-base columns")
            reader.fieldnames = headers
            rows = list(reader)
            if any(None in row for row in rows):
                raise ValueError(
                    "CSV contains extra cells; quote comma-separated keywords"
                )
            return rows
