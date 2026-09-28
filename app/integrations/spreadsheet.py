"""Read-only spreadsheet adapters; authentication is owned by the caller."""

import csv
from pathlib import Path
from typing import Any, Protocol

COLUMNS = ("topic", "keywords", "answer", "enabled", "priority")


class SpreadsheetFormatError(ValueError):
    """Describe an invalid record without retaining its cell contents."""

    def __init__(self, tab: str, row: int, reason: str):
        """Attach safe worksheet coordinates and a fixed diagnostic message."""
        super().__init__(reason)
        self.tab = tab
        self.row = row
        self.reason = reason


class SpreadsheetReader(Protocol):
    def get_tab_names(self) -> list[str]:
        """List available worksheet titles without modifying the source."""
        ...

    def get_all(self, tab_name: str) -> list[dict[str, Any]]:
        """Return data rows in sheet order, excluding the header row."""
        ...


class GoogleSheetsReader:
    """Accept a pre-authenticated Google Sheets v4 discovery service.

    Only read methods are used. Provision the client with the
    spreadsheets.readonly scope outside this adapter; no credential files are read.
    Columns A:E follow the original Thanos layout; row 1 is a header.
    """

    def __init__(self, service: Any, spreadsheet_id: str):
        """Bind an already-authenticated client to a nonempty spreadsheet ID."""
        if not spreadsheet_id.strip():
            raise ValueError("Spreadsheet ID is required")
        self.service = service
        self.spreadsheet_id = spreadsheet_id

    def get_tab_names(self) -> list[str]:
        """Fetch sheet titles using only the required metadata fields."""
        document = (
            self.service.spreadsheets()
            .get(spreadsheetId=self.spreadsheet_id, fields="sheets.properties.title")
            .execute()
        )
        return [sheet["properties"]["title"] for sheet in document.get("sheets", [])]

    def get_all(self, tab_name: str) -> list[dict[str, Any]]:
        """Read columns A:E after the header, safely quoting the sheet title."""
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
        """Remember the export path without opening or modifying it."""
        self.path = path

    def get_tab_names(self) -> list[str]:
        """Expose the single CSV worksheet as Sheet1."""
        return ["Sheet1"]

    def get_all(self, tab_name: str) -> list[dict[str, Any]]:
        """Validate the CSV layout and retain blank records for row reporting."""
        if tab_name != "Sheet1":
            raise ValueError("CSV exports contain a single tab: Sheet1")
        with self.path.open(encoding="utf-8-sig", newline="") as source:
            reader = csv.reader(source, strict=True)
            row_number = 1
            try:
                headers = [name.strip().lower() for name in next(reader, [])]
                if len(set(headers)) != len(headers) or set(headers) != set(COLUMNS):
                    raise SpreadsheetFormatError(
                        tab_name, 1, "CSV must contain the five knowledge-base columns"
                    )
                rows = []
                row_number = 2
                for values in reader:
                    if len(values) > len(headers):
                        raise SpreadsheetFormatError(
                            tab_name,
                            row_number,
                            "CSV contains extra cells; quote comma-separated keywords",
                        )
                    rows.append(dict(zip(headers, values)))
                    row_number += 1
            except csv.Error as error:
                raise SpreadsheetFormatError(
                    tab_name, row_number, "Malformed CSV quoting"
                ) from error
            return rows
