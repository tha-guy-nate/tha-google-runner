from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from googleapiclient.errors import HttpError

from tha_google_runner.errors import GoogleError
from tha_google_runner.sheets import ThaSheets

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DEFAULT_META = [{"properties": {"title": "Sheet1", "sheetId": 0}}]


def make_mock_service(
    *,
    values: list[list[Any]] | None = None,
    spreadsheet_id: str = "sheet-id",
    meta_sheets: list[dict[str, Any]] | None = None,
) -> MagicMock:
    service = MagicMock()
    service.spreadsheets.return_value.get.return_value.execute.return_value = {
        "sheets": meta_sheets or _DEFAULT_META
    }
    service.spreadsheets.return_value.values.return_value.get.return_value.execute.return_value = {
        "values": values or []
    }
    service.spreadsheets.return_value.create.return_value.execute.return_value = {
        "spreadsheetId": spreadsheet_id
    }
    return service


def make_sheets(
    service: MagicMock, *, drive: MagicMock | None = None, **kwargs: Any
) -> ThaSheets:
    sheets = ThaSheets(**kwargs)
    sheets._service = service
    if drive is not None:
        sheets._drive_service = drive
    return sheets


def _vals(service: MagicMock) -> MagicMock:
    return service.spreadsheets.return_value.values.return_value


def make_http_error(status: int) -> HttpError:
    resp = MagicMock()
    resp.status = status
    return HttpError(resp=resp, content=b"Error")


# ---------------------------------------------------------------------------
# _resolve_id
# ---------------------------------------------------------------------------


def test_resolve_id_accepts_raw_id() -> None:
    service = make_mock_service(values=[["name"], ["Alice"]])
    sheets = make_sheets(service)
    sheets.read(spreadsheet_id="sheet-id", sheet_name="Sheet1")
    call_kwargs = _vals(service).get.call_args.kwargs
    assert call_kwargs["spreadsheetId"] == "sheet-id"


def test_resolve_id_accepts_full_url() -> None:
    service = make_mock_service(values=[["name"], ["Alice"]])
    sheets = make_sheets(service)
    url = "https://docs.google.com/spreadsheets/d/abc123/edit#gid=0"
    sheets.read(url=url, sheet_name="Sheet1")
    call_kwargs = _vals(service).get.call_args.kwargs
    assert call_kwargs["spreadsheetId"] == "abc123"


def test_resolve_id_raises_on_invalid_url() -> None:
    service = make_mock_service()
    sheets = make_sheets(service)
    with pytest.raises(GoogleError, match="Could not parse"):
        sheets.read(url="https://google.com/not-a-sheet")


def test_resolve_id_raises_when_neither_provided() -> None:
    service = make_mock_service()
    sheets = make_sheets(service)
    with pytest.raises(GoogleError, match="Provide either"):
        sheets.read()


# ---------------------------------------------------------------------------
# read
# ---------------------------------------------------------------------------


def test_read_returns_records() -> None:
    service = make_mock_service(values=[["name", "age"], ["Alice", 30]])
    sheets = make_sheets(service)
    result = sheets.read(spreadsheet_id="sheet-id", sheet_name="Sheet1")
    assert result == [{"name": "Alice", "age": 30}]


def test_read_sets_self_rows() -> None:
    service = make_mock_service(values=[["a"], ["1"]])
    sheets = make_sheets(service)
    sheets.read(spreadsheet_id="sheet-id", sheet_name="Sheet1")
    assert sheets.rows == [{"a": "1"}]


def test_read_empty_sheet_returns_empty_list() -> None:
    service = make_mock_service(values=[])
    sheets = make_sheets(service)
    result = sheets.read(spreadsheet_id="sheet-id", sheet_name="Sheet1")
    assert result == []


def test_read_pads_short_rows() -> None:
    service = make_mock_service(values=[["a", "b", "c"], ["x"]])
    sheets = make_sheets(service)
    result = sheets.read(spreadsheet_id="sheet-id", sheet_name="Sheet1")
    assert result == [{"a": "x", "b": "", "c": ""}]


def test_read_uses_named_sheet() -> None:
    service = make_mock_service(values=[])
    sheets = make_sheets(service)
    sheets.read(spreadsheet_id="sheet-id", sheet_name="Data")
    call_kwargs = _vals(service).get.call_args.kwargs
    assert "'Data'" in call_kwargs["range"]


def test_read_resolves_first_sheet_when_name_omitted() -> None:
    service = make_mock_service(values=[])
    sheets = make_sheets(service)
    sheets.read(spreadsheet_id="sheet-id")
    call_kwargs = _vals(service).get.call_args.kwargs
    assert "'Sheet1'" in call_kwargs["range"]


def test_read_raises_on_missing_spreadsheet() -> None:
    service = make_mock_service()
    service.spreadsheets.return_value.get.return_value.execute.side_effect = make_http_error(404)
    sheets = make_sheets(service)
    with pytest.raises(GoogleError):
        sheets.read(spreadsheet_id="bad-id")


def test_read_raises_on_missing_sheet_name() -> None:
    service = make_mock_service()
    _vals(service).get.return_value.execute.side_effect = make_http_error(400)
    sheets = make_sheets(service)
    with pytest.raises(GoogleError):
        sheets.read(spreadsheet_id="sheet-id", sheet_name="Nope")


# ---------------------------------------------------------------------------
# append_rows
# ---------------------------------------------------------------------------


def test_append_rows_with_existing_headers() -> None:
    service = make_mock_service(values=[["name", "age"]])
    sheets = make_sheets(service)
    count = sheets.append_rows(
        [{"name": "Bob", "age": 25}], spreadsheet_id="sheet-id", sheet_name="Sheet1"
    )
    assert count == 1
    _vals(service).append.assert_called_once_with(
        spreadsheetId="sheet-id",
        range="'Sheet1'",
        valueInputOption="USER_ENTERED",
        insertDataOption="INSERT_ROWS",
        body={"values": [["Bob", 25]]},
    )


def test_append_rows_empty_sheet_writes_headers_and_data_in_one_call() -> None:
    service = make_mock_service(values=[])
    sheets = make_sheets(service)
    sheets.append_rows(
        [{"name": "Alice", "score": 99}], spreadsheet_id="sheet-id", sheet_name="Sheet1"
    )
    _vals(service).update.assert_called_once_with(
        spreadsheetId="sheet-id",
        range="'Sheet1'!A1",
        valueInputOption="USER_ENTERED",
        body={"values": [["name", "score"], ["Alice", 99]]},
    )
    _vals(service).append.assert_not_called()


def test_append_rows_missing_key_fills_empty_string() -> None:
    service = make_mock_service(values=[["name", "age", "email"]])
    sheets = make_sheets(service)
    sheets.append_rows([{"name": "Alice"}], spreadsheet_id="sheet-id", sheet_name="Sheet1")
    _vals(service).append.assert_called_once_with(
        spreadsheetId="sheet-id",
        range="'Sheet1'",
        valueInputOption="USER_ENTERED",
        insertDataOption="INSERT_ROWS",
        body={"values": [["Alice", "", ""]]},
    )


def test_append_rows_empty_list_is_no_op() -> None:
    service = make_mock_service()
    sheets = make_sheets(service)
    count = sheets.append_rows([], spreadsheet_id="sheet-id", sheet_name="Sheet1")
    assert count == 0
    _vals(service).append.assert_not_called()


def test_append_rows_sets_self_rows() -> None:
    service = make_mock_service(values=[["x"]])
    sheets = make_sheets(service)
    rows = [{"x": 1}]
    sheets.append_rows(rows, spreadsheet_id="sheet-id", sheet_name="Sheet1")
    assert sheets.rows is rows


# ---------------------------------------------------------------------------
# update_rows
# ---------------------------------------------------------------------------


def test_update_rows_clears_and_writes() -> None:
    service = make_mock_service()
    sheets = make_sheets(service)
    rows = [{"x": 1, "y": 2}]
    count = sheets.update_rows(rows, spreadsheet_id="sheet-id", sheet_name="Sheet1")
    _vals(service).clear.assert_called_once_with(
        spreadsheetId="sheet-id", range="'Sheet1'"
    )
    _vals(service).update.assert_called_once_with(
        spreadsheetId="sheet-id",
        range="'Sheet1'!A1",
        valueInputOption="USER_ENTERED",
        body={"values": [["x", "y"], [1, 2]]},
    )
    assert count == 1


def test_update_rows_empty_clears_only() -> None:
    service = make_mock_service()
    sheets = make_sheets(service)
    count = sheets.update_rows([], spreadsheet_id="sheet-id", sheet_name="Sheet1")
    _vals(service).clear.assert_called_once()
    _vals(service).update.assert_not_called()
    assert count == 0
    assert sheets.rows == []


def test_update_rows_sets_self_rows() -> None:
    service = make_mock_service()
    sheets = make_sheets(service)
    rows = [{"a": 1}]
    sheets.update_rows(rows, spreadsheet_id="sheet-id", sheet_name="Sheet1")
    assert sheets.rows is rows


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------


def test_create_returns_spreadsheet_id() -> None:
    service = make_mock_service(spreadsheet_id="new-sheet-id")
    sheets = make_sheets(service)
    sid = sheets.create("My Sheet")
    assert sid == "new-sheet-id"
    service.spreadsheets.return_value.create.assert_called_once_with(
        body={
            "properties": {"title": "My Sheet"},
            "sheets": [{"properties": {"title": "Sheet1"}}],
        }
    )


def test_create_uses_custom_sheet_name() -> None:
    service = make_mock_service()
    sheets = make_sheets(service)
    sheets.create("My Sheet", sheet_name="Data")
    body = service.spreadsheets.return_value.create.call_args.kwargs["body"]
    assert body["sheets"][0]["properties"]["title"] == "Data"


def test_create_with_rows_writes_data() -> None:
    service = make_mock_service()
    sheets = make_sheets(service)
    rows = [{"col": "val"}]
    sheets.create("My Sheet", rows=rows)
    _vals(service).update.assert_called_once_with(
        spreadsheetId="sheet-id",
        range="'Sheet1'!A1",
        valueInputOption="USER_ENTERED",
        body={"values": [["col"], ["val"]]},
    )


def test_create_no_rows_does_not_write() -> None:
    service = make_mock_service()
    sheets = make_sheets(service)
    sheets.create("My Sheet")
    _vals(service).update.assert_not_called()


# ---------------------------------------------------------------------------
# clear
# ---------------------------------------------------------------------------


def test_clear_clears_sheet() -> None:
    service = make_mock_service()
    sheets = make_sheets(service)
    sheets.rows = [{"a": "1"}]
    sheets.clear(spreadsheet_id="sheet-id", sheet_name="Sheet1")
    _vals(service).clear.assert_called_once_with(
        spreadsheetId="sheet-id", range="'Sheet1'"
    )
    assert sheets.rows == []


def test_clear_uses_named_sheet() -> None:
    service = make_mock_service()
    sheets = make_sheets(service)
    sheets.clear(spreadsheet_id="sheet-id", sheet_name="Archive")
    call_kwargs = _vals(service).clear.call_args.kwargs
    assert "'Archive'" in call_kwargs["range"]


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------


def test_delete_calls_drive_files_delete() -> None:
    service = make_mock_service()
    drive = MagicMock()
    sheets = make_sheets(service, drive=drive)
    sheets.rows = [{"a": "1"}]
    sheets.delete(spreadsheet_id="sheet-id")
    drive.files.return_value.delete.assert_called_once_with(fileId="sheet-id")
    assert sheets.rows == []


# ---------------------------------------------------------------------------
# list_sheets
# ---------------------------------------------------------------------------


def test_list_sheets_returns_names() -> None:
    service = make_mock_service(
        meta_sheets=[
            {"properties": {"title": "Sheet1", "sheetId": 0}},
            {"properties": {"title": "Data", "sheetId": 1}},
        ]
    )
    sheets = make_sheets(service)
    names = sheets.list_sheets(spreadsheet_id="sheet-id")
    assert names == ["Sheet1", "Data"]


def test_list_sheets_raises_on_missing_spreadsheet() -> None:
    service = make_mock_service()
    service.spreadsheets.return_value.get.return_value.execute.side_effect = make_http_error(404)
    sheets = make_sheets(service)
    with pytest.raises(GoogleError):
        sheets.list_sheets(spreadsheet_id="bad-id")


# ---------------------------------------------------------------------------
# add_sheet
# ---------------------------------------------------------------------------


def test_add_sheet_creates_worksheet() -> None:
    service = make_mock_service()
    sheets = make_sheets(service)
    sheets.add_sheet("NewSheet", spreadsheet_id="sheet-id")
    call_body = service.spreadsheets.return_value.batchUpdate.call_args.kwargs["body"]
    assert call_body["requests"][0]["addSheet"]["properties"]["title"] == "NewSheet"
    _vals(service).update.assert_not_called()


def test_add_sheet_with_rows_writes_data() -> None:
    service = make_mock_service()
    sheets = make_sheets(service)
    rows = [{"x": 1, "y": 2}]
    sheets.add_sheet("NewSheet", spreadsheet_id="sheet-id", rows=rows)
    _vals(service).update.assert_called_once_with(
        spreadsheetId="sheet-id",
        range="'NewSheet'!A1",
        valueInputOption="USER_ENTERED",
        body={"values": [["x", "y"], [1, 2]]},
    )
    assert sheets.rows is rows


# ---------------------------------------------------------------------------
# delete_sheet
# ---------------------------------------------------------------------------


def test_delete_sheet_sends_delete_request() -> None:
    service = make_mock_service()
    sheets = make_sheets(service)
    sheets.delete_sheet("Sheet1", spreadsheet_id="sheet-id")
    call_body = service.spreadsheets.return_value.batchUpdate.call_args.kwargs["body"]
    assert call_body["requests"][0]["deleteSheet"]["sheetId"] == 0


def test_delete_sheet_raises_on_missing_sheet() -> None:
    service = make_mock_service()
    sheets = make_sheets(service)
    with pytest.raises(GoogleError):
        sheets.delete_sheet("Nope", spreadsheet_id="sheet-id")


# ---------------------------------------------------------------------------
# share
# ---------------------------------------------------------------------------


def test_share_defaults_to_reader() -> None:
    service = make_mock_service()
    drive = MagicMock()
    sheets = make_sheets(service, drive=drive)
    sheets.share("alice@example.com", spreadsheet_id="sheet-id")
    drive.permissions.return_value.create.assert_called_once_with(
        fileId="sheet-id",
        body={"type": "user", "role": "reader", "emailAddress": "alice@example.com"},
        sendNotificationEmail=False,
    )


def test_share_custom_role() -> None:
    service = make_mock_service()
    drive = MagicMock()
    sheets = make_sheets(service, drive=drive)
    sheets.share("bob@example.com", spreadsheet_id="sheet-id", role="writer")
    drive.permissions.return_value.create.assert_called_once_with(
        fileId="sheet-id",
        body={"type": "user", "role": "writer", "emailAddress": "bob@example.com"},
        sendNotificationEmail=False,
    )


# ---------------------------------------------------------------------------
# upsert_rows
# ---------------------------------------------------------------------------

_HEADERS = ["id", "name", "score"]
_DATA = [["1", "Alice", "95"], ["2", "Bob", "82"]]


def _upsert_service(
    headers: list[str] = _HEADERS,
    data: list[list[str]] = _DATA,
) -> MagicMock:
    return make_mock_service(values=[headers, *data])


def test_upsert_empty_sheet_writes_all() -> None:
    service = make_mock_service(values=[])
    rows = [{"id": "1", "name": "Alice"}]
    sheets = make_sheets(service)
    count = sheets.upsert_rows(rows, key="id", spreadsheet_id="sheet-id", sheet_name="Sheet1")
    _vals(service).update.assert_called_once_with(
        spreadsheetId="sheet-id",
        range="'Sheet1'!A1",
        valueInputOption="USER_ENTERED",
        body={"values": [["id", "name"], ["1", "Alice"]]},
    )
    assert count == 1


def test_upsert_all_new_rows_appended() -> None:
    service = _upsert_service()
    rows = [{"id": "3", "name": "Carol", "score": "77"}]
    sheets = make_sheets(service)
    count = sheets.upsert_rows(rows, key="id", spreadsheet_id="sheet-id", sheet_name="Sheet1")
    _vals(service).append.assert_called_once_with(
        spreadsheetId="sheet-id",
        range="'Sheet1'",
        valueInputOption="USER_ENTERED",
        insertDataOption="INSERT_ROWS",
        body={"values": [["3", "Carol", "77"]]},
    )
    assert count == 1


def test_upsert_patches_matching_row() -> None:
    service = _upsert_service()
    sheets = make_sheets(service)
    sheets.upsert_rows(
        [{"id": "1", "score": "100"}], key="id", spreadsheet_id="sheet-id", sheet_name="Sheet1"
    )
    call_body = _vals(service).batchUpdate.call_args.kwargs["body"]
    assert call_body["data"] == [
        {"range": "'Sheet1'!A2", "values": [["1"]]},
        {"range": "'Sheet1'!C2", "values": [["100"]]},
    ]
    _vals(service).append.assert_not_called()


def test_upsert_composite_key_matches() -> None:
    service = make_mock_service(
        values=[
            ["region", "id", "score"],
            ["us", "1", "95"],
            ["eu", "1", "80"],
        ]
    )
    rows = [{"region": "eu", "id": "1", "score": "99"}]
    sheets = make_sheets(service)
    sheets.upsert_rows(rows, key=["region", "id"], spreadsheet_id="sheet-id", sheet_name="Sheet1")
    call_body = _vals(service).batchUpdate.call_args.kwargs["body"]
    assert call_body["data"] == [
        {"range": "'Sheet1'!A3", "values": [["eu"]]},
        {"range": "'Sheet1'!B3", "values": [["1"]]},
        {"range": "'Sheet1'!C3", "values": [["99"]]},
    ]


def test_upsert_on_conflict_update_all() -> None:
    service = make_mock_service(values=[["id", "score"], ["1", "95"], ["1", "82"]])
    sheets = make_sheets(service)
    count = sheets.upsert_rows(
        [{"id": "1", "score": "99"}],
        key="id",
        spreadsheet_id="sheet-id",
        sheet_name="Sheet1",
        on_conflict="update_all",
    )
    call_body = _vals(service).batchUpdate.call_args.kwargs["body"]
    patched_rows = {u["range"][-1] for u in call_body["data"]}
    assert "2" in patched_rows and "3" in patched_rows
    assert count == 1


def test_upsert_on_conflict_update_first() -> None:
    service = make_mock_service(values=[["id", "v"], ["1", "a"], ["1", "b"]])
    sheets = make_sheets(service)
    sheets.upsert_rows(
        [{"id": "1", "v": "z"}],
        key="id",
        spreadsheet_id="sheet-id",
        sheet_name="Sheet1",
        on_conflict="update_first",
    )
    call_body = _vals(service).batchUpdate.call_args.kwargs["body"]
    assert all("2" in u["range"] for u in call_body["data"])


def test_upsert_on_conflict_update_last() -> None:
    service = make_mock_service(values=[["id", "v"], ["1", "a"], ["1", "b"]])
    sheets = make_sheets(service)
    sheets.upsert_rows(
        [{"id": "1", "v": "z"}],
        key="id",
        spreadsheet_id="sheet-id",
        sheet_name="Sheet1",
        on_conflict="update_last",
    )
    call_body = _vals(service).batchUpdate.call_args.kwargs["body"]
    assert all("3" in u["range"] for u in call_body["data"])


def test_upsert_on_conflict_raise() -> None:
    service = make_mock_service(values=[["id", "v"], ["1", "a"], ["1", "b"]])
    sheets = make_sheets(service)
    with pytest.raises(GoogleError, match="Duplicate"):
        sheets.upsert_rows(
            [{"id": "1", "v": "z"}],
            key="id",
            spreadsheet_id="sheet-id",
            sheet_name="Sheet1",
            on_conflict="raise",
        )


def test_upsert_on_conflict_skip() -> None:
    service = make_mock_service(values=[["id", "v"], ["1", "a"], ["1", "b"]])
    sheets = make_sheets(service)
    count = sheets.upsert_rows(
        [{"id": "1", "v": "z"}],
        key="id",
        spreadsheet_id="sheet-id",
        sheet_name="Sheet1",
        on_conflict="skip",
    )
    _vals(service).batchUpdate.assert_not_called()
    assert count == 0


def test_upsert_new_columns_added_to_header() -> None:
    service = _upsert_service()
    sheets = make_sheets(service)
    sheets.upsert_rows(
        [{"id": "1", "score": "99", "grade": "A"}],
        key="id",
        spreadsheet_id="sheet-id",
        sheet_name="Sheet1",
    )
    _vals(service).update.assert_called_once_with(
        spreadsheetId="sheet-id",
        range="'Sheet1'!A1",
        valueInputOption="USER_ENTERED",
        body={"values": [["id", "name", "score", "grade"]]},
    )


def test_upsert_missing_key_column_raises() -> None:
    service = _upsert_service()
    sheets = make_sheets(service)
    with pytest.raises(GoogleError, match="Key column"):
        sheets.upsert_rows(
            [{"bad_key": "1"}], key="bad_key", spreadsheet_id="sheet-id", sheet_name="Sheet1"
        )


def test_upsert_empty_rows_is_no_op() -> None:
    service = make_mock_service()
    sheets = make_sheets(service)
    count = sheets.upsert_rows([], key="id", spreadsheet_id="sheet-id", sheet_name="Sheet1")
    assert count == 0
    _vals(service).get.assert_not_called()


def test_upsert_sets_self_rows() -> None:
    service = make_mock_service(values=[])
    rows = [{"id": "1"}]
    sheets = make_sheets(service)
    sheets.upsert_rows(rows, key="id", spreadsheet_id="sheet-id", sheet_name="Sheet1")
    assert sheets.rows is rows


# ---------------------------------------------------------------------------
# list[list] input — header auto-detection
# ---------------------------------------------------------------------------


def test_append_rows_list_input_matching_header_dropped() -> None:
    service = make_mock_service(values=[["name", "age"]])
    sheets = make_sheets(service)
    count = sheets.append_rows(
        [["name", "age"], ["Alice", "30"]], spreadsheet_id="sheet-id", sheet_name="Sheet1"
    )
    _vals(service).append.assert_called_once_with(
        spreadsheetId="sheet-id",
        range="'Sheet1'",
        valueInputOption="USER_ENTERED",
        insertDataOption="INSERT_ROWS",
        body={"values": [["Alice", "30"]]},
    )
    assert count == 1


def test_append_rows_list_input_no_header_row() -> None:
    service = make_mock_service(values=[["name", "age"]])
    sheets = make_sheets(service)
    count = sheets.append_rows(
        [["Alice", "30"], ["Bob", "25"]], spreadsheet_id="sheet-id", sheet_name="Sheet1"
    )
    _vals(service).append.assert_called_once_with(
        spreadsheetId="sheet-id",
        range="'Sheet1'",
        valueInputOption="USER_ENTERED",
        insertDataOption="INSERT_ROWS",
        body={"values": [["Alice", "30"], ["Bob", "25"]]},
    )
    assert count == 2


def test_append_rows_list_input_empty_sheet_writes_header_and_data_in_one_call() -> None:
    service = make_mock_service(values=[])
    sheets = make_sheets(service)
    sheets.append_rows(
        [["name", "age"], ["Alice", "30"]], spreadsheet_id="sheet-id", sheet_name="Sheet1"
    )
    _vals(service).update.assert_called_once_with(
        spreadsheetId="sheet-id",
        range="'Sheet1'!A1",
        valueInputOption="USER_ENTERED",
        body={"values": [["name", "age"], ["Alice", "30"]]},
    )
    _vals(service).append.assert_not_called()


def test_update_rows_list_input_first_row_becomes_headers() -> None:
    service = make_mock_service()
    sheets = make_sheets(service)
    count = sheets.update_rows([["x", "y"], [1, 2]], spreadsheet_id="sheet-id", sheet_name="Sheet1")
    _vals(service).update.assert_called_once_with(
        spreadsheetId="sheet-id",
        range="'Sheet1'!A1",
        valueInputOption="USER_ENTERED",
        body={"values": [["x", "y"], [1, 2]]},
    )
    assert count == 1


def test_upsert_rows_list_input_matching_header_dropped() -> None:
    service = _upsert_service()
    sheets = make_sheets(service)
    count = sheets.upsert_rows(
        [["id", "name", "score"], ["3", "Carol", "77"]],
        key="id",
        spreadsheet_id="sheet-id",
        sheet_name="Sheet1",
    )
    _vals(service).append.assert_called_once()
    assert count == 1


def test_upsert_rows_list_input_no_header_row() -> None:
    service = _upsert_service()
    sheets = make_sheets(service)
    count = sheets.upsert_rows(
        [["3", "Carol", "77"]], key="id", spreadsheet_id="sheet-id", sheet_name="Sheet1"
    )
    _vals(service).append.assert_called_once()
    assert count == 1


def test_upsert_rows_list_input_empty_sheet() -> None:
    service = make_mock_service(values=[])
    sheets = make_sheets(service)
    count = sheets.upsert_rows(
        [["id", "name"], ["1", "Alice"]],
        key="id",
        spreadsheet_id="sheet-id",
        sheet_name="Sheet1",
    )
    _vals(service).update.assert_called_once_with(
        spreadsheetId="sheet-id",
        range="'Sheet1'!A1",
        valueInputOption="USER_ENTERED",
        body={"values": [["id", "name"], ["1", "Alice"]]},
    )
    assert count == 1


def test_add_sheet_list_input() -> None:
    service = make_mock_service()
    sheets = make_sheets(service)
    sheets.add_sheet("NewSheet", spreadsheet_id="sheet-id", rows=[["x", "y"], [1, 2]])
    _vals(service).update.assert_called_once_with(
        spreadsheetId="sheet-id",
        range="'NewSheet'!A1",
        valueInputOption="USER_ENTERED",
        body={"values": [["x", "y"], [1, 2]]},
    )


def test_create_list_input() -> None:
    service = make_mock_service()
    sheets = make_sheets(service)
    sheets.create("My Sheet", rows=[["col"], ["val"]])
    _vals(service).update.assert_called_once_with(
        spreadsheetId="sheet-id",
        range="'Sheet1'!A1",
        valueInputOption="USER_ENTERED",
        body={"values": [["col"], ["val"]]},
    )


# ---------------------------------------------------------------------------
# service caching
# ---------------------------------------------------------------------------


def test_service_is_built_once() -> None:
    mock_service = make_mock_service(values=[])
    mock_creds = MagicMock()
    with (
        patch("tha_google_runner.sheets.build_credentials", return_value=mock_creds) as mock_build,
        patch("googleapiclient.discovery.build", return_value=mock_service),
    ):
        sheets = ThaSheets()
        sheets.read(spreadsheet_id="sheet-id", sheet_name="Sheet1")
        sheets.read(spreadsheet_id="sheet-id", sheet_name="Sheet1")
    assert mock_build.call_count == 1
