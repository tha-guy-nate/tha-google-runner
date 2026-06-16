from __future__ import annotations

import re
from typing import Any, Literal, cast

import gspread
import gspread.exceptions
from gspread.utils import rowcol_to_a1

from tha_google_runner.auth import build_credentials
from tha_google_runner.errors import GoogleError

OnConflict = Literal["update_all", "update_first", "update_last", "raise", "skip"]

_URL_RE = re.compile(r"/spreadsheets/d/([a-zA-Z0-9_-]+)")


class ThaSheets:
    def __init__(
        self,
        *,
        credentials_file: str | None = None,
        token_file: str | None = None,
    ) -> None:
        self._credentials_file = credentials_file
        self._token_file = token_file
        self._client: gspread.Client | None = None
        self.rows: list[dict[str, Any]] = []

    def _get_client(self) -> gspread.Client:
        if self._client is None:
            creds = build_credentials(self._credentials_file, self._token_file)
            self._client = gspread.Client(auth=creds)
        return self._client

    def _resolve_id(self, spreadsheet_id: str | None, url: str | None) -> str:
        if url is not None:
            m = _URL_RE.search(url)
            if not m:
                raise GoogleError(f"Could not parse spreadsheet ID from URL: {url}")
            return m.group(1)
        if spreadsheet_id is not None:
            return spreadsheet_id
        raise GoogleError("Provide either spreadsheet_id= or url=")

    def _get_spreadsheet(self, sid: str) -> gspread.Spreadsheet:
        client = self._get_client()
        try:
            return client.open_by_key(sid)
        except gspread.exceptions.SpreadsheetNotFound:
            raise GoogleError(f"Spreadsheet not found: {sid}") from None

    def _get_worksheet(self, sid: str, sheet_name: str | None) -> gspread.Worksheet:
        spreadsheet = self._get_spreadsheet(sid)
        if sheet_name is None:
            return spreadsheet.sheet1
        try:
            return spreadsheet.worksheet(sheet_name)
        except gspread.exceptions.WorksheetNotFound:
            raise GoogleError(f"Sheet '{sheet_name}' not found in {sid}") from None

    def _normalize_rows(
        self,
        rows: list[dict[str, Any]] | list[list[Any]],
        existing_headers: list[str],
    ) -> tuple[list[str], list[dict[str, Any]]]:
        """Convert rows to list[dict] and detect/drop an included header row.

        For list[dict] input, keys become headers (unchanged behavior).
        For list[list] input, auto-detects if rows[0] is a header row by comparing
        it against existing_headers. If they match exactly, the header row is dropped.
        When existing_headers is empty (new/replaced sheet), rows[0] is always headers.
        """
        if not rows:
            return existing_headers, []
        if isinstance(rows[0], dict):
            dict_rows = cast(list[dict[str, Any]], rows)
            headers = existing_headers if existing_headers else list(dict_rows[0].keys())
            return headers, dict_rows
        list_rows = cast(list[list[Any]], rows)
        first_as_strs = [str(v) for v in list_rows[0]]
        if existing_headers:
            if first_as_strs == existing_headers:
                headers = existing_headers
                data = list_rows[1:]
            else:
                headers = existing_headers
                data = list_rows
        else:
            headers = first_as_strs
            data = list_rows[1:]
        return headers, [dict(zip(headers, row, strict=False)) for row in data]

    def read(
        self,
        *,
        spreadsheet_id: str | None = None,
        url: str | None = None,
        sheet_name: str | None = None,
    ) -> list[dict[str, Any]]:
        sid = self._resolve_id(spreadsheet_id, url)
        ws = self._get_worksheet(sid, sheet_name)
        self.rows = ws.get_all_records()
        return self.rows

    def append_rows(
        self,
        rows: list[dict[str, Any]] | list[list[Any]],
        *,
        spreadsheet_id: str | None = None,
        url: str | None = None,
        sheet_name: str | None = None,
    ) -> int:
        if not rows:
            return 0
        sid = self._resolve_id(spreadsheet_id, url)
        ws = self._get_worksheet(sid, sheet_name)
        existing_headers = ws.row_values(1)
        headers, dict_rows = self._normalize_rows(rows, existing_headers)
        if not existing_headers:
            ws.append_row(headers)
        values = [[row.get(h, "") for h in headers] for row in dict_rows]
        ws.append_rows(values)
        self.rows = dict_rows
        return len(dict_rows)

    def update_rows(
        self,
        rows: list[dict[str, Any]] | list[list[Any]],
        *,
        spreadsheet_id: str | None = None,
        url: str | None = None,
        sheet_name: str | None = None,
    ) -> int:
        sid = self._resolve_id(spreadsheet_id, url)
        ws = self._get_worksheet(sid, sheet_name)
        ws.clear()
        if not rows:
            self.rows = []
            return 0
        headers, dict_rows = self._normalize_rows(rows, [])
        values = [headers] + [[row.get(h, "") for h in headers] for row in dict_rows]
        ws.update("A1", values)  # type: ignore[arg-type]
        self.rows = dict_rows
        return len(dict_rows)

    def create(
        self,
        title: str,
        *,
        rows: list[dict[str, Any]] | list[list[Any]] | None = None,
        sheet_name: str = "Sheet1",
    ) -> str:
        client = self._get_client()
        spreadsheet = client.create(title)
        ws = spreadsheet.sheet1
        ws.update_title(sheet_name)
        if rows:
            headers, dict_rows = self._normalize_rows(rows, [])
            values = [headers] + [[row.get(h, "") for h in headers] for row in dict_rows]
            ws.update("A1", values)  # type: ignore[arg-type]
            self.rows = dict_rows
        return spreadsheet.id

    def delete(
        self,
        *,
        spreadsheet_id: str | None = None,
        url: str | None = None,
    ) -> None:
        sid = self._resolve_id(spreadsheet_id, url)
        self._get_client().del_spreadsheet(sid)
        self.rows = []

    def list_sheets(
        self,
        *,
        spreadsheet_id: str | None = None,
        url: str | None = None,
    ) -> list[str]:
        sid = self._resolve_id(spreadsheet_id, url)
        spreadsheet = self._get_spreadsheet(sid)
        return [ws.title for ws in spreadsheet.worksheets()]

    def add_sheet(
        self,
        sheet_name: str,
        *,
        spreadsheet_id: str | None = None,
        url: str | None = None,
        rows: list[dict[str, Any]] | list[list[Any]] | None = None,
    ) -> None:
        sid = self._resolve_id(spreadsheet_id, url)
        spreadsheet = self._get_spreadsheet(sid)
        ws = spreadsheet.add_worksheet(title=sheet_name, rows=1000, cols=26)
        if rows:
            headers, dict_rows = self._normalize_rows(rows, [])
            values = [headers] + [[row.get(h, "") for h in headers] for row in dict_rows]
            ws.update("A1", values)  # type: ignore[arg-type]
            self.rows = dict_rows

    def delete_sheet(
        self,
        sheet_name: str,
        *,
        spreadsheet_id: str | None = None,
        url: str | None = None,
    ) -> None:
        sid = self._resolve_id(spreadsheet_id, url)
        spreadsheet = self._get_spreadsheet(sid)
        try:
            ws = spreadsheet.worksheet(sheet_name)
        except gspread.exceptions.WorksheetNotFound:
            raise GoogleError(f"Sheet '{sheet_name}' not found in {sid}") from None
        spreadsheet.del_worksheet(ws)

    def share(
        self,
        email: str,
        *,
        spreadsheet_id: str | None = None,
        url: str | None = None,
        role: str = "reader",
    ) -> None:
        sid = self._resolve_id(spreadsheet_id, url)
        spreadsheet = self._get_spreadsheet(sid)
        spreadsheet.share(email, perm_type="user", role=role)

    def upsert_rows(
        self,
        rows: list[dict[str, Any]] | list[list[Any]],
        *,
        key: str | list[str],
        spreadsheet_id: str | None = None,
        url: str | None = None,
        sheet_name: str | None = None,
        on_conflict: OnConflict = "update_all",
    ) -> int:
        if not rows:
            return 0

        sid = self._resolve_id(spreadsheet_id, url)
        ws = self._get_worksheet(sid, sheet_name)
        keys = [key] if isinstance(key, str) else list(key)

        existing = ws.get_all_values()
        existing_hdrs: list[str] = list(existing[0]) if existing else []
        norm_hdrs, dict_rows = self._normalize_rows(rows, existing_hdrs)

        # Empty sheet — write everything fresh
        if not existing:
            values = [norm_hdrs] + [[row.get(h, "") for h in norm_hdrs] for row in dict_rows]
            ws.update("A1", values)  # type: ignore[arg-type]
            self.rows = dict_rows
            return len(dict_rows)

        headers = list(existing[0])
        data_rows = existing[1:]

        missing_keys = [k for k in keys if k not in headers]
        if missing_keys:
            raise GoogleError(f"Key column(s) not found in sheet headers: {missing_keys}")

        # Collect new columns from incoming rows, preserving order
        seen: set[str] = set(headers)
        new_cols: list[str] = []
        for row in dict_rows:
            for col in row:
                if col not in seen:
                    new_cols.append(col)
                    seen.add(col)
        if new_cols:
            headers = headers + new_cols
            ws.update("A1", [headers])  # type: ignore[arg-type]

        col_index = {h: i for i, h in enumerate(headers)}
        key_col_indices = [col_index[k] for k in keys]

        # Build key → list of sheet row numbers (1-indexed, data starts at row 2)
        index: dict[tuple[str, ...], list[int]] = {}
        for i, row_vals in enumerate(data_rows):
            row_key = tuple(str(row_vals[c]) if c < len(row_vals) else "" for c in key_col_indices)
            index.setdefault(row_key, []).append(i + 2)

        cell_updates: list[dict[str, Any]] = []
        rows_to_append: list[list[Any]] = []
        upserted = 0

        for row in dict_rows:
            row_key = tuple(str(row.get(k, "")) for k in keys)
            matches = index.get(row_key, [])

            if not matches:
                rows_to_append.append([row.get(h, "") for h in headers])
                upserted += 1
                continue

            if len(matches) > 1:
                if on_conflict == "raise":
                    raise GoogleError(
                        f"Duplicate rows found for key {dict(zip(keys, row_key, strict=True))}"
                    )
                elif on_conflict == "skip":
                    continue
                elif on_conflict == "update_first":
                    matches = [matches[0]]
                elif on_conflict == "update_last":
                    matches = [matches[-1]]
                # update_all: use all matches as-is

            for sheet_row in matches:
                for col_name, val in row.items():
                    if col_name in col_index:
                        cell = rowcol_to_a1(sheet_row, col_index[col_name] + 1)
                        cell_updates.append({"range": cell, "values": [[val]]})
            upserted += 1

        if cell_updates:
            ws.batch_update(cell_updates)
        if rows_to_append:
            ws.append_rows(rows_to_append)

        self.rows = dict_rows
        return upserted

    def clear(
        self,
        *,
        spreadsheet_id: str | None = None,
        url: str | None = None,
        sheet_name: str | None = None,
    ) -> None:
        sid = self._resolve_id(spreadsheet_id, url)
        ws = self._get_worksheet(sid, sheet_name)
        ws.clear()
        self.rows = []
