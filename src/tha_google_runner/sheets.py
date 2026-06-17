from __future__ import annotations

import re
from typing import Any, ClassVar, Literal, cast

from googleapiclient.errors import HttpError

from tha_google_runner.auth import SCOPE_DRIVE, SCOPE_SPREADSHEETS, build_credentials
from tha_google_runner.errors import GoogleError, with_retry

OnConflict = Literal["update_all", "update_first", "update_last", "raise", "skip"]

_URL_RE = re.compile(r"/spreadsheets/d/([a-zA-Z0-9_-]+)")
_INPUT = "USER_ENTERED"


def _a1(row: int, col: int) -> str:
    col_str = ""
    c = col
    while c > 0:
        c, rem = divmod(c - 1, 26)
        col_str = chr(65 + rem) + col_str
    return f"{col_str}{row}"


def _rng(name: str, a1: str = "") -> str:
    safe = name.replace("'", "\\'")
    return f"'{safe}'!{a1}" if a1 else f"'{safe}'"


class ThaSheets:
    _SCOPES: ClassVar[list[str]] = [SCOPE_SPREADSHEETS, SCOPE_DRIVE]

    def __init__(
        self,
        *,
        credentials_file: str | None = None,
        token_file: str | None = None,
        scopes: list[str] | None = None,
    ) -> None:
        self._credentials_file = credentials_file
        self._token_file = token_file
        self._scopes = scopes if scopes is not None else self._SCOPES
        self._service: Any = None
        self._drive_service: Any = None
        self.rows: list[dict[str, Any]] = []

    def _get_service(self) -> Any:
        if self._service is None:
            from googleapiclient.discovery import build

            creds = build_credentials(self._credentials_file, self._token_file, self._scopes)
            self._service = build("sheets", "v4", credentials=creds)
        return self._service

    def _get_drive_service(self) -> Any:
        if self._drive_service is None:
            from googleapiclient.discovery import build

            creds = build_credentials(self._credentials_file, self._token_file, self._scopes)
            self._drive_service = build("drive", "v3", credentials=creds)
        return self._drive_service

    def _resolve_id(self, spreadsheet_id: str | None, url: str | None) -> str:
        if url is not None:
            m = _URL_RE.search(url)
            if not m:
                raise GoogleError(f"Could not parse spreadsheet ID from URL: {url}")
            return m.group(1)
        if spreadsheet_id is not None:
            return spreadsheet_id
        raise GoogleError("Provide either spreadsheet_id= or url=")

    def _meta(self, sid: str, fields: str = "*") -> dict[str, Any]:
        try:
            return with_retry(
                lambda: (
                    self._get_service()
                    .spreadsheets()
                    .get(spreadsheetId=sid, fields=fields)
                    .execute()
                )
            )
        except HttpError as exc:
            if exc.resp.status == 404:
                raise GoogleError(f"Spreadsheet not found: {sid}") from None
            raise

    def _resolve_sheet(self, sid: str, sheet_name: str | None) -> str:
        if sheet_name is not None:
            return sheet_name
        result = self._meta(sid, fields="sheets.properties.title")
        sheets = result.get("sheets", [])
        if not sheets:
            raise GoogleError(f"Spreadsheet {sid} has no sheets")
        return sheets[0]["properties"]["title"]

    def _get_values(
        self, sid: str, range_: str, *, sheet_name: str | None = None
    ) -> list[list[Any]]:
        try:
            result = with_retry(
                lambda: (
                    self._get_service()
                    .spreadsheets()
                    .values()
                    .get(
                        spreadsheetId=sid,
                        range=range_,
                        valueRenderOption="UNFORMATTED_VALUE",
                    )
                    .execute()
                )
            )
            return result.get("values", [])
        except HttpError as exc:
            if exc.resp.status in (400, 404) and sheet_name is not None:
                raise GoogleError(f"Sheet '{sheet_name}' not found in {sid}") from None
            raise

    def _set_values(self, sid: str, range_: str, values: list[list[Any]]) -> None:
        with_retry(
            lambda: (
                self._get_service()
                .spreadsheets()
                .values()
                .update(
                    spreadsheetId=sid,
                    range=range_,
                    valueInputOption=_INPUT,
                    body={"values": values},
                )
                .execute()
            )
        )

    def _append_values(self, sid: str, range_: str, values: list[list[Any]]) -> None:
        with_retry(
            lambda: (
                self._get_service()
                .spreadsheets()
                .values()
                .append(
                    spreadsheetId=sid,
                    range=range_,
                    valueInputOption=_INPUT,
                    insertDataOption="INSERT_ROWS",
                    body={"values": values},
                )
                .execute()
            )
        )

    def _clear_values(self, sid: str, range_: str) -> None:
        with_retry(
            lambda: (
                self._get_service()
                .spreadsheets()
                .values()
                .clear(spreadsheetId=sid, range=range_)
                .execute()
            )
        )

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
        name = self._resolve_sheet(sid, sheet_name)
        raw = self._get_values(sid, _rng(name), sheet_name=name)
        if not raw:
            self.rows = []
            return self.rows
        headers = [str(h) for h in raw[0]]
        self.rows = [
            dict(zip(headers, row + [""] * (len(headers) - len(row)), strict=False))
            for row in raw[1:]
        ]
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
        name = self._resolve_sheet(sid, sheet_name)
        header_raw = self._get_values(sid, _rng(name, "1:1"), sheet_name=name)
        existing_headers = [str(h) for h in header_raw[0]] if header_raw else []
        headers, dict_rows = self._normalize_rows(rows, existing_headers)
        values = [[row.get(h, "") for h in headers] for row in dict_rows]
        if not existing_headers:
            self._set_values(sid, _rng(name, "A1"), [headers, *values])
        else:
            self._append_values(sid, _rng(name), values)
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
        name = self._resolve_sheet(sid, sheet_name)
        self._clear_values(sid, _rng(name))
        if not rows:
            self.rows = []
            return 0
        headers, dict_rows = self._normalize_rows(rows, [])
        values = [headers, *[[row.get(h, "") for h in headers] for row in dict_rows]]
        self._set_values(sid, _rng(name, "A1"), values)
        self.rows = dict_rows
        return len(dict_rows)

    def create(
        self,
        title: str,
        *,
        rows: list[dict[str, Any]] | list[list[Any]] | None = None,
        sheet_name: str = "Sheet1",
    ) -> str:
        body: dict[str, Any] = {
            "properties": {"title": title},
            "sheets": [{"properties": {"title": sheet_name}}],
        }
        result = with_retry(lambda: self._get_service().spreadsheets().create(body=body).execute())
        sid: str = result["spreadsheetId"]
        if rows:
            headers, dict_rows = self._normalize_rows(rows, [])
            values = [headers, *[[row.get(h, "") for h in headers] for row in dict_rows]]
            self._set_values(sid, _rng(sheet_name, "A1"), values)
            self.rows = dict_rows
        return sid

    def delete(
        self,
        *,
        spreadsheet_id: str | None = None,
        url: str | None = None,
    ) -> None:
        sid = self._resolve_id(spreadsheet_id, url)
        with_retry(lambda: self._get_drive_service().files().delete(fileId=sid).execute())
        self.rows = []

    def list_sheets(
        self,
        *,
        spreadsheet_id: str | None = None,
        url: str | None = None,
    ) -> list[str]:
        sid = self._resolve_id(spreadsheet_id, url)
        result = self._meta(sid, fields="sheets.properties.title")
        return [s["properties"]["title"] for s in result.get("sheets", [])]

    def add_sheet(
        self,
        sheet_name: str,
        *,
        spreadsheet_id: str | None = None,
        url: str | None = None,
        rows: list[dict[str, Any]] | list[list[Any]] | None = None,
    ) -> None:
        sid = self._resolve_id(spreadsheet_id, url)
        with_retry(
            lambda: (
                self._get_service()
                .spreadsheets()
                .batchUpdate(
                    spreadsheetId=sid,
                    body={
                        "requests": [
                            {
                                "addSheet": {
                                    "properties": {
                                        "title": sheet_name,
                                        "gridProperties": {"rowCount": 1000, "columnCount": 26},
                                    }
                                }
                            }
                        ]
                    },
                )
                .execute()
            )
        )
        if rows:
            headers, dict_rows = self._normalize_rows(rows, [])
            values = [headers, *[[row.get(h, "") for h in headers] for row in dict_rows]]
            self._set_values(sid, _rng(sheet_name, "A1"), values)
            self.rows = dict_rows

    def delete_sheet(
        self,
        sheet_name: str,
        *,
        spreadsheet_id: str | None = None,
        url: str | None = None,
    ) -> None:
        sid = self._resolve_id(spreadsheet_id, url)
        result = self._meta(sid, fields="sheets.properties")
        sheet_id: int | None = None
        for s in result.get("sheets", []):
            if s["properties"]["title"] == sheet_name:
                sheet_id = s["properties"]["sheetId"]
                break
        if sheet_id is None:
            raise GoogleError(f"Sheet '{sheet_name}' not found in {sid}")
        with_retry(
            lambda: (
                self._get_service()
                .spreadsheets()
                .batchUpdate(
                    spreadsheetId=sid,
                    body={"requests": [{"deleteSheet": {"sheetId": sheet_id}}]},
                )
                .execute()
            )
        )

    def share(
        self,
        email: str,
        *,
        spreadsheet_id: str | None = None,
        url: str | None = None,
        role: str = "reader",
    ) -> None:
        sid = self._resolve_id(spreadsheet_id, url)
        with_retry(
            lambda: (
                self._get_drive_service()
                .permissions()
                .create(
                    fileId=sid,
                    body={"type": "user", "role": role, "emailAddress": email},
                    sendNotificationEmail=False,
                )
                .execute()
            )
        )

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
        name = self._resolve_sheet(sid, sheet_name)
        keys = [key] if isinstance(key, str) else list(key)

        existing = self._get_values(sid, _rng(name), sheet_name=name)
        existing_hdrs: list[str] = [str(h) for h in existing[0]] if existing else []
        norm_hdrs, dict_rows = self._normalize_rows(rows, existing_hdrs)

        if not existing:
            values = [norm_hdrs] + [[row.get(h, "") for h in norm_hdrs] for row in dict_rows]
            self._set_values(sid, _rng(name, "A1"), values)
            self.rows = dict_rows
            return len(dict_rows)

        headers = [str(h) for h in existing[0]]
        data_rows = existing[1:]

        missing_keys = [k for k in keys if k not in headers]
        if missing_keys:
            raise GoogleError(f"Key column(s) not found in sheet headers: {missing_keys}")

        seen: set[str] = set(headers)
        new_cols: list[str] = []
        for row in dict_rows:
            for col in row:
                if col not in seen:
                    new_cols.append(col)
                    seen.add(col)
        if new_cols:
            headers = headers + new_cols
            self._set_values(sid, _rng(name, "A1"), [headers])

        col_index = {h: i for i, h in enumerate(headers)}
        key_col_indices = [col_index[k] for k in keys]

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

            for sheet_row in matches:
                for col_name, val in row.items():
                    if col_name in col_index:
                        cell = _a1(sheet_row, col_index[col_name] + 1)
                        cell_updates.append({"range": _rng(name, cell), "values": [[val]]})
            upserted += 1

        if cell_updates:
            with_retry(
                lambda: (
                    self._get_service()
                    .spreadsheets()
                    .values()
                    .batchUpdate(
                        spreadsheetId=sid,
                        body={"valueInputOption": _INPUT, "data": cell_updates},
                    )
                    .execute()
                )
            )
        if rows_to_append:
            self._append_values(sid, _rng(name), rows_to_append)

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
        name = self._resolve_sheet(sid, sheet_name)
        self._clear_values(sid, _rng(name))
        self.rows = []
