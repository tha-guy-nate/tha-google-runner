from unittest.mock import MagicMock, patch

import gspread.exceptions
import pytest

from tha_google_runner.errors import GoogleError
from tha_google_runner.sheets import ThaSheets

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_mock_client(
    records: list | None = None,
    row1: list | None = None,
    spreadsheet_id: str = "sheet-id-123",
) -> tuple[MagicMock, MagicMock, MagicMock]:
    ws = MagicMock()
    ws.get_all_records.return_value = records or []
    ws.row_values.return_value = row1 or []

    spreadsheet = MagicMock()
    spreadsheet.sheet1 = ws
    spreadsheet.worksheet.return_value = ws
    spreadsheet.id = spreadsheet_id

    client = MagicMock()
    client.open_by_key.return_value = spreadsheet
    client.create.return_value = spreadsheet

    return client, ws, spreadsheet


def make_sheets(client: MagicMock, **kwargs: object) -> ThaSheets:
    sheets = ThaSheets(**kwargs)
    sheets._client = client  # inject mock; bypasses auth
    return sheets


# ---------------------------------------------------------------------------
# _resolve_id
# ---------------------------------------------------------------------------

def test_resolve_id_accepts_raw_id() -> None:
    client, _, _ = make_mock_client(records=[])
    sheets = make_sheets(client)
    sheets.read(spreadsheet_id="sheet-id")
    client.open_by_key.assert_called_once_with("sheet-id")


def test_resolve_id_accepts_full_url() -> None:
    client, _, _ = make_mock_client(records=[])
    sheets = make_sheets(client)
    url = "https://docs.google.com/spreadsheets/d/abc123/edit#gid=0"
    sheets.read(url=url)
    client.open_by_key.assert_called_once_with("abc123")


def test_resolve_id_raises_on_invalid_url() -> None:
    client, _, _ = make_mock_client()
    sheets = make_sheets(client)
    with pytest.raises(GoogleError, match="Could not parse"):
        sheets.read(url="https://google.com/not-a-sheet")


def test_resolve_id_raises_when_neither_provided() -> None:
    client, _, _ = make_mock_client()
    sheets = make_sheets(client)
    with pytest.raises(GoogleError, match="Provide either"):
        sheets.read()


# ---------------------------------------------------------------------------
# read
# ---------------------------------------------------------------------------

def test_read_returns_records() -> None:
    client, _ws, _ = make_mock_client(records=[{"name": "Alice", "age": 30}])
    sheets = make_sheets(client)
    result = sheets.read(spreadsheet_id="sheet-id")
    assert result == [{"name": "Alice", "age": 30}]


def test_read_sets_self_rows() -> None:
    client, _ws, _ = make_mock_client(records=[{"a": "1"}])
    sheets = make_sheets(client)
    sheets.read(spreadsheet_id="sheet-id")
    assert sheets.rows == [{"a": "1"}]


def test_read_empty_sheet_returns_empty_list() -> None:
    client, _, _ = make_mock_client(records=[])
    sheets = make_sheets(client)
    result = sheets.read(spreadsheet_id="sheet-id")
    assert result == []


def test_read_uses_named_sheet() -> None:
    client, _, spreadsheet = make_mock_client(records=[])
    sheets = make_sheets(client)
    sheets.read(spreadsheet_id="sheet-id", sheet_name="Data")
    spreadsheet.worksheet.assert_called_once_with("Data")


def test_read_raises_on_missing_spreadsheet() -> None:
    client = MagicMock()
    client.open_by_key.side_effect = gspread.exceptions.SpreadsheetNotFound
    sheets = make_sheets(client)
    with pytest.raises(GoogleError):
        sheets.read(spreadsheet_id="bad-id")


def test_read_raises_on_missing_sheet_name() -> None:
    client, _, spreadsheet = make_mock_client()
    spreadsheet.worksheet.side_effect = gspread.exceptions.WorksheetNotFound
    sheets = make_sheets(client)
    with pytest.raises(GoogleError):
        sheets.read(spreadsheet_id="sheet-id", sheet_name="Nope")


# ---------------------------------------------------------------------------
# append_rows
# ---------------------------------------------------------------------------

def test_append_rows_with_existing_headers() -> None:
    client, ws, _ = make_mock_client(row1=["name", "age"])
    sheets = make_sheets(client)
    count = sheets.append_rows([{"name": "Bob", "age": 25}], spreadsheet_id="sheet-id")
    assert count == 1
    ws.append_rows.assert_called_once_with([["Bob", 25]])


def test_append_rows_empty_sheet_writes_headers_first() -> None:
    client, ws, _ = make_mock_client(row1=[])
    sheets = make_sheets(client)
    sheets.append_rows([{"name": "Alice", "score": 99}], spreadsheet_id="sheet-id")
    ws.append_row.assert_called_once_with(["name", "score"])


def test_append_rows_missing_key_fills_empty_string() -> None:
    client, ws, _ = make_mock_client(row1=["name", "age", "email"])
    sheets = make_sheets(client)
    sheets.append_rows([{"name": "Alice"}], spreadsheet_id="sheet-id")
    ws.append_rows.assert_called_once_with([["Alice", "", ""]])


def test_append_rows_empty_list_is_no_op() -> None:
    client, ws, _ = make_mock_client()
    sheets = make_sheets(client)
    count = sheets.append_rows([], spreadsheet_id="sheet-id")
    assert count == 0
    ws.append_rows.assert_not_called()


def test_append_rows_sets_self_rows() -> None:
    client, _ws, _ = make_mock_client(row1=["x"])
    sheets = make_sheets(client)
    rows = [{"x": 1}]
    sheets.append_rows(rows, spreadsheet_id="sheet-id")
    assert sheets.rows is rows


# ---------------------------------------------------------------------------
# update_rows
# ---------------------------------------------------------------------------

def test_update_rows_clears_and_writes() -> None:
    client, ws, _ = make_mock_client()
    sheets = make_sheets(client)
    rows = [{"x": 1, "y": 2}]
    count = sheets.update_rows(rows, spreadsheet_id="sheet-id")
    ws.clear.assert_called_once()
    ws.update.assert_called_once_with("A1", [["x", "y"], [1, 2]])
    assert count == 1


def test_update_rows_empty_clears_only() -> None:
    client, ws, _ = make_mock_client()
    sheets = make_sheets(client)
    count = sheets.update_rows([], spreadsheet_id="sheet-id")
    ws.clear.assert_called_once()
    ws.update.assert_not_called()
    assert count == 0
    assert sheets.rows == []


def test_update_rows_sets_self_rows() -> None:
    client, _ws, _ = make_mock_client()
    sheets = make_sheets(client)
    rows = [{"a": 1}]
    sheets.update_rows(rows, spreadsheet_id="sheet-id")
    assert sheets.rows is rows


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------

def test_create_returns_spreadsheet_id() -> None:
    client, _, _ = make_mock_client(spreadsheet_id="new-sheet-id")
    sheets = make_sheets(client)
    sid = sheets.create("My Sheet")
    assert sid == "new-sheet-id"
    client.create.assert_called_once_with("My Sheet")


def test_create_renames_sheet() -> None:
    client, ws, _ = make_mock_client()
    sheets = make_sheets(client)
    sheets.create("My Sheet", sheet_name="Data")
    ws.update_title.assert_called_once_with("Data")


def test_create_with_rows_writes_data() -> None:
    client, ws, _ = make_mock_client()
    sheets = make_sheets(client)
    rows = [{"col": "val"}]
    sheets.create("My Sheet", rows=rows)
    ws.update.assert_called_once_with("A1", [["col"], ["val"]])


def test_create_no_rows_does_not_write() -> None:
    client, ws, _ = make_mock_client()
    sheets = make_sheets(client)
    sheets.create("My Sheet")
    ws.update.assert_not_called()


# ---------------------------------------------------------------------------
# clear
# ---------------------------------------------------------------------------

def test_clear_calls_ws_clear() -> None:
    client, ws, _ = make_mock_client()
    sheets = make_sheets(client)
    sheets.rows = [{"a": "1"}]
    sheets.clear(spreadsheet_id="sheet-id")
    ws.clear.assert_called_once()
    assert sheets.rows == []


def test_clear_uses_named_sheet() -> None:
    client, _, spreadsheet = make_mock_client()
    sheets = make_sheets(client)
    sheets.clear(spreadsheet_id="sheet-id", sheet_name="Archive")
    spreadsheet.worksheet.assert_called_once_with("Archive")


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------

def test_delete_calls_del_spreadsheet() -> None:
    client, _, _ = make_mock_client()
    sheets = make_sheets(client)
    sheets.rows = [{"a": "1"}]
    sheets.delete(spreadsheet_id="sheet-id")
    client.del_spreadsheet.assert_called_once_with("sheet-id")
    assert sheets.rows == []


# ---------------------------------------------------------------------------
# list_sheets
# ---------------------------------------------------------------------------

def test_list_sheets_returns_names() -> None:
    client, _, spreadsheet = make_mock_client()
    ws1, ws2 = MagicMock(), MagicMock()
    ws1.title = "Sheet1"
    ws2.title = "Data"
    spreadsheet.worksheets.return_value = [ws1, ws2]
    sheets = make_sheets(client)
    names = sheets.list_sheets(spreadsheet_id="sheet-id")
    assert names == ["Sheet1", "Data"]


def test_list_sheets_raises_on_missing_spreadsheet() -> None:
    client = MagicMock()
    client.open_by_key.side_effect = gspread.exceptions.SpreadsheetNotFound
    sheets = make_sheets(client)
    with pytest.raises(GoogleError):
        sheets.list_sheets(spreadsheet_id="bad-id")


# ---------------------------------------------------------------------------
# add_sheet
# ---------------------------------------------------------------------------

def test_add_sheet_creates_worksheet() -> None:
    client, _, spreadsheet = make_mock_client()
    new_ws = MagicMock()
    spreadsheet.add_worksheet.return_value = new_ws
    sheets = make_sheets(client)
    sheets.add_sheet("NewSheet", spreadsheet_id="sheet-id")
    spreadsheet.add_worksheet.assert_called_once_with(title="NewSheet", rows=1000, cols=26)
    new_ws.update.assert_not_called()


def test_add_sheet_with_rows_writes_data() -> None:
    client, _, spreadsheet = make_mock_client()
    new_ws = MagicMock()
    spreadsheet.add_worksheet.return_value = new_ws
    rows = [{"x": 1, "y": 2}]
    sheets = make_sheets(client)
    sheets.add_sheet("NewSheet", spreadsheet_id="sheet-id", rows=rows)
    new_ws.update.assert_called_once_with("A1", [["x", "y"], [1, 2]])
    assert sheets.rows is rows


# ---------------------------------------------------------------------------
# delete_sheet
# ---------------------------------------------------------------------------

def test_delete_sheet_calls_del_worksheet() -> None:
    client, ws, spreadsheet = make_mock_client()
    sheets = make_sheets(client)
    sheets.delete_sheet("Sheet1", spreadsheet_id="sheet-id")
    spreadsheet.del_worksheet.assert_called_once_with(ws)


def test_delete_sheet_raises_on_missing_sheet() -> None:
    client, _, spreadsheet = make_mock_client()
    spreadsheet.worksheet.side_effect = gspread.exceptions.WorksheetNotFound
    sheets = make_sheets(client)
    with pytest.raises(GoogleError):
        sheets.delete_sheet("Nope", spreadsheet_id="sheet-id")


# ---------------------------------------------------------------------------
# share
# ---------------------------------------------------------------------------

def test_share_defaults_to_reader() -> None:
    client, _, spreadsheet = make_mock_client()
    sheets = make_sheets(client)
    sheets.share("alice@example.com", spreadsheet_id="sheet-id")
    spreadsheet.share.assert_called_once_with("alice@example.com", perm_type="user", role="reader")


def test_share_custom_role() -> None:
    client, _, spreadsheet = make_mock_client()
    sheets = make_sheets(client)
    sheets.share("bob@example.com", spreadsheet_id="sheet-id", role="writer")
    spreadsheet.share.assert_called_once_with("bob@example.com", perm_type="user", role="writer")


# ---------------------------------------------------------------------------
# upsert_rows
# ---------------------------------------------------------------------------

_HEADERS = ["id", "name", "score"]
_DATA = [["1", "Alice", "95"], ["2", "Bob", "82"]]


def _ws_with_data(
    ws: MagicMock,
    headers: list[str] = _HEADERS,
    data: list[list[str]] = _DATA,
) -> MagicMock:
    ws.get_all_values.return_value = [headers, *data]
    return ws


def test_upsert_empty_sheet_writes_all() -> None:
    client, ws, _ = make_mock_client()
    ws.get_all_values.return_value = []
    rows = [{"id": "1", "name": "Alice"}]
    sheets = make_sheets(client)
    count = sheets.upsert_rows(rows, key="id", spreadsheet_id="sheet-id")
    ws.update.assert_called_once_with("A1", [["id", "name"], ["1", "Alice"]])
    assert count == 1


def test_upsert_all_new_rows_appended() -> None:
    client, ws, _ = make_mock_client()
    _ws_with_data(ws)
    rows = [{"id": "3", "name": "Carol", "score": "77"}]
    sheets = make_sheets(client)
    count = sheets.upsert_rows(rows, key="id", spreadsheet_id="sheet-id")
    ws.append_rows.assert_called_once_with([["3", "Carol", "77"]])
    assert count == 1


def test_upsert_patches_matching_row() -> None:
    client, ws, _ = make_mock_client()
    _ws_with_data(ws)
    sheets = make_sheets(client)
    sheets.upsert_rows([{"id": "1", "score": "100"}], key="id", spreadsheet_id="sheet-id")
    ws.batch_update.assert_called_once_with([
        {"range": "A2", "values": [["1"]]},
        {"range": "C2", "values": [["100"]]},
    ])
    ws.append_rows.assert_not_called()


def test_upsert_composite_key_matches() -> None:
    client, ws, _ = make_mock_client()
    ws.get_all_values.return_value = [
        ["region", "id", "score"],
        ["us", "1", "95"],
        ["eu", "1", "80"],
    ]
    rows = [{"region": "eu", "id": "1", "score": "99"}]
    sheets = make_sheets(client)
    sheets.upsert_rows(rows, key=["region", "id"], spreadsheet_id="sheet-id")
    ws.batch_update.assert_called_once_with([
        {"range": "A3", "values": [["eu"]]},
        {"range": "B3", "values": [["1"]]},
        {"range": "C3", "values": [["99"]]},
    ])


def test_upsert_on_conflict_update_all() -> None:
    client, ws, _ = make_mock_client()
    ws.get_all_values.return_value = [
        ["id", "score"],
        ["1", "95"],
        ["1", "82"],
    ]
    sheets = make_sheets(client)
    count = sheets.upsert_rows(
        [{"id": "1", "score": "99"}],
        key="id",
        spreadsheet_id="sheet-id",
        on_conflict="update_all",
    )
    updates = ws.batch_update.call_args[0][0]
    patched_rows = {u["range"][-1] for u in updates}
    assert "2" in patched_rows and "3" in patched_rows
    assert count == 1


def test_upsert_on_conflict_update_first() -> None:
    client, ws, _ = make_mock_client()
    ws.get_all_values.return_value = [["id", "v"], ["1", "a"], ["1", "b"]]
    sheets = make_sheets(client)
    sheets.upsert_rows(
        [{"id": "1", "v": "z"}], key="id", spreadsheet_id="sheet-id", on_conflict="update_first"
    )
    updates = ws.batch_update.call_args[0][0]
    assert all("2" in u["range"] for u in updates)


def test_upsert_on_conflict_update_last() -> None:
    client, ws, _ = make_mock_client()
    ws.get_all_values.return_value = [["id", "v"], ["1", "a"], ["1", "b"]]
    sheets = make_sheets(client)
    sheets.upsert_rows(
        [{"id": "1", "v": "z"}], key="id", spreadsheet_id="sheet-id", on_conflict="update_last"
    )
    updates = ws.batch_update.call_args[0][0]
    assert all("3" in u["range"] for u in updates)


def test_upsert_on_conflict_raise() -> None:
    client, ws, _ = make_mock_client()
    ws.get_all_values.return_value = [["id", "v"], ["1", "a"], ["1", "b"]]
    sheets = make_sheets(client)
    with pytest.raises(GoogleError, match="Duplicate"):
        sheets.upsert_rows(
            [{"id": "1", "v": "z"}], key="id", spreadsheet_id="sheet-id", on_conflict="raise"
        )


def test_upsert_on_conflict_skip() -> None:
    client, ws, _ = make_mock_client()
    ws.get_all_values.return_value = [["id", "v"], ["1", "a"], ["1", "b"]]
    sheets = make_sheets(client)
    count = sheets.upsert_rows(
        [{"id": "1", "v": "z"}], key="id", spreadsheet_id="sheet-id", on_conflict="skip"
    )
    ws.batch_update.assert_not_called()
    assert count == 0


def test_upsert_new_columns_added_to_header() -> None:
    client, ws, _ = make_mock_client()
    _ws_with_data(ws)
    sheets = make_sheets(client)
    sheets.upsert_rows(
        [{"id": "1", "score": "99", "grade": "A"}], key="id", spreadsheet_id="sheet-id"
    )
    ws.update.assert_called_once_with("A1", [["id", "name", "score", "grade"]])


def test_upsert_missing_key_column_raises() -> None:
    client, ws, _ = make_mock_client()
    _ws_with_data(ws)
    sheets = make_sheets(client)
    with pytest.raises(GoogleError, match="Key column"):
        sheets.upsert_rows(
            [{"bad_key": "1"}], key="bad_key", spreadsheet_id="sheet-id"
        )


def test_upsert_empty_rows_is_no_op() -> None:
    client, ws, _ = make_mock_client()
    sheets = make_sheets(client)
    count = sheets.upsert_rows([], key="id", spreadsheet_id="sheet-id")
    assert count == 0
    ws.get_all_values.assert_not_called()


def test_upsert_sets_self_rows() -> None:
    client, ws, _ = make_mock_client()
    ws.get_all_values.return_value = []
    rows = [{"id": "1"}]
    sheets = make_sheets(client)
    sheets.upsert_rows(rows, key="id", spreadsheet_id="sheet-id")
    assert sheets.rows is rows


# ---------------------------------------------------------------------------
# list[list] input — header auto-detection
# ---------------------------------------------------------------------------

def test_append_rows_list_input_matching_header_dropped() -> None:
    client, ws, _ = make_mock_client(row1=["name", "age"])
    sheets = make_sheets(client)
    count = sheets.append_rows(
        [["name", "age"], ["Alice", "30"]], spreadsheet_id="sheet-id"
    )
    ws.append_rows.assert_called_once_with([["Alice", "30"]])
    assert count == 1


def test_append_rows_list_input_no_header_row() -> None:
    client, ws, _ = make_mock_client(row1=["name", "age"])
    sheets = make_sheets(client)
    count = sheets.append_rows(
        [["Alice", "30"], ["Bob", "25"]], spreadsheet_id="sheet-id"
    )
    ws.append_rows.assert_called_once_with([["Alice", "30"], ["Bob", "25"]])
    assert count == 2


def test_append_rows_list_input_empty_sheet_writes_header() -> None:
    client, ws, _ = make_mock_client(row1=[])
    sheets = make_sheets(client)
    sheets.append_rows([["name", "age"], ["Alice", "30"]], spreadsheet_id="sheet-id")
    ws.append_row.assert_called_once_with(["name", "age"])
    ws.append_rows.assert_called_once_with([["Alice", "30"]])


def test_update_rows_list_input_first_row_becomes_headers() -> None:
    client, ws, _ = make_mock_client()
    sheets = make_sheets(client)
    count = sheets.update_rows([["x", "y"], [1, 2]], spreadsheet_id="sheet-id")
    ws.update.assert_called_once_with("A1", [["x", "y"], [1, 2]])
    assert count == 1


def test_upsert_rows_list_input_matching_header_dropped() -> None:
    client, ws, _ = make_mock_client()
    _ws_with_data(ws)
    sheets = make_sheets(client)
    count = sheets.upsert_rows(
        [["id", "name", "score"], ["3", "Carol", "77"]],
        key="id",
        spreadsheet_id="sheet-id",
    )
    ws.append_rows.assert_called_once_with([["3", "Carol", "77"]])
    assert count == 1


def test_upsert_rows_list_input_no_header_row() -> None:
    client, ws, _ = make_mock_client()
    _ws_with_data(ws)
    sheets = make_sheets(client)
    count = sheets.upsert_rows(
        [["3", "Carol", "77"]], key="id", spreadsheet_id="sheet-id"
    )
    ws.append_rows.assert_called_once_with([["3", "Carol", "77"]])
    assert count == 1


def test_upsert_rows_list_input_empty_sheet() -> None:
    client, ws, _ = make_mock_client()
    ws.get_all_values.return_value = []
    sheets = make_sheets(client)
    count = sheets.upsert_rows(
        [["id", "name"], ["1", "Alice"]], key="id", spreadsheet_id="sheet-id"
    )
    ws.update.assert_called_once_with("A1", [["id", "name"], ["1", "Alice"]])
    assert count == 1


def test_add_sheet_list_input() -> None:
    client, _, spreadsheet = make_mock_client()
    new_ws = MagicMock()
    spreadsheet.add_worksheet.return_value = new_ws
    sheets = make_sheets(client)
    sheets.add_sheet("NewSheet", spreadsheet_id="sheet-id", rows=[["x", "y"], [1, 2]])
    new_ws.update.assert_called_once_with("A1", [["x", "y"], [1, 2]])


def test_create_list_input() -> None:
    client, ws, _ = make_mock_client()
    sheets = make_sheets(client)
    sheets.create("My Sheet", rows=[["col"], ["val"]])
    ws.update.assert_called_once_with("A1", [["col"], ["val"]])


# ---------------------------------------------------------------------------
# client caching
# ---------------------------------------------------------------------------

def test_client_is_built_once() -> None:
    client, _, _ = make_mock_client(records=[])
    mock_creds = MagicMock()
    with (
        patch("tha_google_runner.sheets.build_credentials", return_value=mock_creds) as mock_build,
        patch("tha_google_runner.sheets.gspread.Client", return_value=client),
    ):
        sheets = ThaSheets()
        sheets.read(spreadsheet_id="sheet-id")
        sheets.read(spreadsheet_id="sheet-id")
    assert mock_build.call_count == 1
