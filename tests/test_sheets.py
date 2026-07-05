from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch
from urllib.parse import quote

import pytest

from tha_google_runner._rest import RestClient
from tha_google_runner.errors import GoogleError, GoogleHttpError
from tha_google_runner.sheets import _DRIVE_BASE, _SHEETS_BASE, ThaSheets

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DEFAULT_META = [{"properties": {"title": "Sheet1", "sheetId": 0}}]


def make_mock_rest(
    *,
    values: list[list[Any]] | None = None,
    spreadsheet_id: str = "sheet-id",
    meta_sheets: list[dict[str, Any]] | None = None,
) -> MagicMock:
    rest = MagicMock(spec=RestClient)

    def _get(url: str, **kwargs: Any) -> Any:
        if "/values/" in url:
            return {"values": values if values is not None else []}
        return {"sheets": meta_sheets if meta_sheets is not None else _DEFAULT_META}

    def _post(url: str, **kwargs: Any) -> Any:
        if url == _SHEETS_BASE:
            return {"spreadsheetId": spreadsheet_id}
        return {}

    rest.get.side_effect = _get
    rest.post.side_effect = _post
    rest.put.return_value = {}
    rest.delete.return_value = {}
    return rest


def make_sheets(rest: MagicMock, **kwargs: Any) -> ThaSheets:
    sheets = ThaSheets(**kwargs)
    sheets._rest = rest
    return sheets


def make_http_error(status: int) -> GoogleHttpError:
    return GoogleHttpError(status, None, "Error")


def _values_url(sid: str, range_: str, suffix: str = "") -> str:
    return f"{_SHEETS_BASE}/{sid}/values/{quote(range_, safe='')}{suffix}"


# ---------------------------------------------------------------------------
# _normalize_rows
# ---------------------------------------------------------------------------


def test_normalize_rows_empty_returns_existing_headers() -> None:
    rest = make_mock_rest()
    sheets = make_sheets(rest)
    headers, dict_rows = sheets._normalize_rows([], ["name", "age"])
    assert headers == ["name", "age"]
    assert dict_rows == []


# ---------------------------------------------------------------------------
# _resolve_id
# ---------------------------------------------------------------------------


def test_resolve_id_accepts_raw_id() -> None:
    rest = make_mock_rest(values=[["name"], ["Alice"]])
    sheets = make_sheets(rest)
    sheets.read(spreadsheet_id="sheet-id", sheet_name="Sheet1")
    url = rest.get.call_args_list[0].args[0]
    assert url.startswith(f"{_SHEETS_BASE}/sheet-id/values/")


def test_resolve_id_accepts_full_url() -> None:
    rest = make_mock_rest(values=[["name"], ["Alice"]])
    sheets = make_sheets(rest)
    url = "https://docs.google.com/spreadsheets/d/abc123/edit#gid=0"
    sheets.read(url=url, sheet_name="Sheet1")
    call_url = rest.get.call_args_list[0].args[0]
    assert call_url.startswith(f"{_SHEETS_BASE}/abc123/values/")


def test_resolve_id_raises_on_invalid_url() -> None:
    rest = make_mock_rest()
    sheets = make_sheets(rest)
    with pytest.raises(GoogleError, match="Could not parse"):
        sheets.read(url="https://google.com/not-a-sheet")


def test_resolve_id_raises_when_neither_provided() -> None:
    rest = make_mock_rest()
    sheets = make_sheets(rest)
    with pytest.raises(GoogleError, match="Provide either"):
        sheets.read()


# ---------------------------------------------------------------------------
# read
# ---------------------------------------------------------------------------


def test_read_returns_records() -> None:
    rest = make_mock_rest(values=[["name", "age"], ["Alice", 30]])
    sheets = make_sheets(rest)
    result = sheets.read(spreadsheet_id="sheet-id", sheet_name="Sheet1")
    assert result == [{"name": "Alice", "age": 30}]


def test_read_sets_self_rows() -> None:
    rest = make_mock_rest(values=[["a"], ["1"]])
    sheets = make_sheets(rest)
    sheets.read(spreadsheet_id="sheet-id", sheet_name="Sheet1")
    assert sheets.rows == [{"a": "1"}]


def test_read_empty_sheet_returns_empty_list() -> None:
    rest = make_mock_rest(values=[])
    sheets = make_sheets(rest)
    result = sheets.read(spreadsheet_id="sheet-id", sheet_name="Sheet1")
    assert result == []


def test_read_pads_short_rows() -> None:
    rest = make_mock_rest(values=[["a", "b", "c"], ["x"]])
    sheets = make_sheets(rest)
    result = sheets.read(spreadsheet_id="sheet-id", sheet_name="Sheet1")
    assert result == [{"a": "x", "b": "", "c": ""}]


def test_read_uses_named_sheet() -> None:
    rest = make_mock_rest(values=[])
    sheets = make_sheets(rest)
    sheets.read(spreadsheet_id="sheet-id", sheet_name="Data")
    url = rest.get.call_args_list[0].args[0]
    assert "Data" in url


def test_read_resolves_first_sheet_when_name_omitted() -> None:
    rest = make_mock_rest(values=[])
    sheets = make_sheets(rest)
    sheets.read(spreadsheet_id="sheet-id")
    url = rest.get.call_args_list[-1].args[0]
    assert "Sheet1" in url


def test_read_raises_on_missing_spreadsheet() -> None:
    rest = make_mock_rest()
    rest.get.side_effect = make_http_error(404)
    sheets = make_sheets(rest)
    with pytest.raises(GoogleError):
        sheets.read(spreadsheet_id="bad-id")


def test_read_raises_on_missing_sheet_name() -> None:
    rest = make_mock_rest()

    def _get(url: str, **kwargs: Any) -> Any:
        if "/values/" in url:
            raise make_http_error(400)
        return {"sheets": _DEFAULT_META}

    rest.get.side_effect = _get
    sheets = make_sheets(rest)
    with pytest.raises(GoogleError):
        sheets.read(spreadsheet_id="sheet-id", sheet_name="Nope")


def test_meta_reraises_non_404_http_error() -> None:
    rest = make_mock_rest()
    rest.get.side_effect = make_http_error(500)
    sheets = make_sheets(rest)
    with pytest.raises(GoogleHttpError):
        sheets.read(spreadsheet_id="sheet-id")


def test_get_values_reraises_when_sheet_name_not_given() -> None:
    rest = make_mock_rest()
    rest.get.side_effect = make_http_error(404)
    sheets = make_sheets(rest)
    with pytest.raises(GoogleHttpError):
        sheets._get_values("sheet-id", "Sheet1!A:Z", sheet_name=None)


def test_get_values_reraises_non_400_404_http_error() -> None:
    rest = make_mock_rest()

    def _get(url: str, **kwargs: Any) -> Any:
        if "/values/" in url:
            raise make_http_error(500)
        return {"sheets": _DEFAULT_META}

    rest.get.side_effect = _get
    sheets = make_sheets(rest)
    with pytest.raises(GoogleHttpError):
        sheets.read(spreadsheet_id="sheet-id", sheet_name="Nope")


def test_resolve_sheet_raises_when_no_sheets() -> None:
    rest = make_mock_rest(meta_sheets=[])
    sheets = make_sheets(rest)
    with pytest.raises(GoogleError, match="has no sheets"):
        sheets.read(spreadsheet_id="sheet-id")


# ---------------------------------------------------------------------------
# append_rows
# ---------------------------------------------------------------------------


def test_append_rows_with_existing_headers() -> None:
    rest = make_mock_rest(values=[["name", "age"]])
    sheets = make_sheets(rest)
    count = sheets.append_rows(
        [{"name": "Bob", "age": 25}], spreadsheet_id="sheet-id", sheet_name="Sheet1"
    )
    assert count == 1
    url, kwargs = rest.post.call_args
    assert url[0] == _values_url("sheet-id", "'Sheet1'", ":append")
    assert kwargs["params"] == {
        "valueInputOption": "USER_ENTERED",
        "insertDataOption": "INSERT_ROWS",
    }
    assert kwargs["json"] == {"values": [["Bob", 25]]}


def test_append_rows_empty_sheet_writes_headers_and_data_in_one_call() -> None:
    rest = make_mock_rest(values=[])
    sheets = make_sheets(rest)
    sheets.append_rows(
        [{"name": "Alice", "score": 99}], spreadsheet_id="sheet-id", sheet_name="Sheet1"
    )
    rest.put.assert_called_once()
    url, kwargs = rest.put.call_args
    assert url[0] == _values_url("sheet-id", "'Sheet1'!A1")
    assert kwargs["json"] == {"values": [["name", "score"], ["Alice", 99]]}
    assert not any(":append" in c.args[0] for c in rest.post.call_args_list)


def test_append_rows_missing_key_fills_empty_string() -> None:
    rest = make_mock_rest(values=[["name", "age", "email"]])
    sheets = make_sheets(rest)
    sheets.append_rows([{"name": "Alice"}], spreadsheet_id="sheet-id", sheet_name="Sheet1")
    _, kwargs = rest.post.call_args
    assert kwargs["json"] == {"values": [["Alice", "", ""]]}


def test_append_rows_empty_list_is_no_op() -> None:
    rest = make_mock_rest()
    sheets = make_sheets(rest)
    count = sheets.append_rows([], spreadsheet_id="sheet-id", sheet_name="Sheet1")
    assert count == 0
    rest.post.assert_not_called()


def test_append_rows_sets_self_rows() -> None:
    rest = make_mock_rest(values=[["x"]])
    sheets = make_sheets(rest)
    rows = [{"x": 1}]
    sheets.append_rows(rows, spreadsheet_id="sheet-id", sheet_name="Sheet1")
    assert sheets.rows is rows


# ---------------------------------------------------------------------------
# update_rows
# ---------------------------------------------------------------------------


def test_update_rows_clears_and_writes() -> None:
    rest = make_mock_rest()
    sheets = make_sheets(rest)
    rows = [{"x": 1, "y": 2}]
    count = sheets.update_rows(rows, spreadsheet_id="sheet-id", sheet_name="Sheet1")
    clear_url = rest.post.call_args_list[0].args[0]
    assert clear_url == _values_url("sheet-id", "'Sheet1'", ":clear")
    put_url, put_kwargs = rest.put.call_args
    assert put_url[0] == _values_url("sheet-id", "'Sheet1'!A1")
    assert put_kwargs["json"] == {"values": [["x", "y"], [1, 2]]}
    assert count == 1


def test_update_rows_empty_clears_only() -> None:
    rest = make_mock_rest()
    sheets = make_sheets(rest)
    count = sheets.update_rows([], spreadsheet_id="sheet-id", sheet_name="Sheet1")
    rest.post.assert_called_once()
    rest.put.assert_not_called()
    assert count == 0
    assert sheets.rows == []


def test_update_rows_sets_self_rows() -> None:
    rest = make_mock_rest()
    sheets = make_sheets(rest)
    rows = [{"a": 1}]
    sheets.update_rows(rows, spreadsheet_id="sheet-id", sheet_name="Sheet1")
    assert sheets.rows is rows


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------


def test_create_returns_spreadsheet_id() -> None:
    rest = make_mock_rest(spreadsheet_id="new-sheet-id")
    sheets = make_sheets(rest)
    sid = sheets.create("My Sheet")
    assert sid == "new-sheet-id"
    url, kwargs = rest.post.call_args
    assert url[0] == _SHEETS_BASE
    assert kwargs["json"] == {
        "properties": {"title": "My Sheet"},
        "sheets": [{"properties": {"title": "Sheet1"}}],
    }


def test_create_uses_custom_sheet_name() -> None:
    rest = make_mock_rest()
    sheets = make_sheets(rest)
    sheets.create("My Sheet", sheet_name="Data")
    _, kwargs = rest.post.call_args
    assert kwargs["json"]["sheets"][0]["properties"]["title"] == "Data"


def test_create_with_rows_writes_data() -> None:
    rest = make_mock_rest()
    sheets = make_sheets(rest)
    rows = [{"col": "val"}]
    sheets.create("My Sheet", rows=rows)
    _, kwargs = rest.put.call_args
    assert kwargs["json"] == {"values": [["col"], ["val"]]}


def test_create_no_rows_does_not_write() -> None:
    rest = make_mock_rest()
    sheets = make_sheets(rest)
    sheets.create("My Sheet")
    rest.put.assert_not_called()


# ---------------------------------------------------------------------------
# clear
# ---------------------------------------------------------------------------


def test_clear_clears_sheet() -> None:
    rest = make_mock_rest()
    sheets = make_sheets(rest)
    sheets.rows = [{"a": "1"}]
    sheets.clear(spreadsheet_id="sheet-id", sheet_name="Sheet1")
    url = rest.post.call_args.args[0]
    assert url == _values_url("sheet-id", "'Sheet1'", ":clear")
    assert sheets.rows == []


def test_clear_uses_named_sheet() -> None:
    rest = make_mock_rest()
    sheets = make_sheets(rest)
    sheets.clear(spreadsheet_id="sheet-id", sheet_name="Archive")
    url = rest.post.call_args.args[0]
    assert "Archive" in url


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------


def test_delete_calls_drive_files_delete() -> None:
    rest = make_mock_rest()
    sheets = make_sheets(rest)
    sheets.rows = [{"a": "1"}]
    sheets.delete(spreadsheet_id="sheet-id")
    rest.delete.assert_called_once_with(f"{_DRIVE_BASE}/files/sheet-id")
    assert sheets.rows == []


def test_rest_client_built_and_cached_lazily() -> None:
    sheets = ThaSheets(credentials_file="secret.json", token_file="token.json")
    mock_rest = make_mock_rest()

    with (
        patch("tha_google_runner.sheets.build_credentials") as mock_build_creds,
        patch("tha_google_runner.sheets.RestClient") as mock_rest_cls,
    ):
        mock_build_creds.return_value = "creds"
        mock_rest_cls.return_value = mock_rest
        sheets.delete(spreadsheet_id="sheet-id")
        sheets.delete(spreadsheet_id="sheet-id")

    mock_build_creds.assert_called_once_with("secret.json", "token.json", sheets._scopes)
    mock_rest_cls.assert_called_once_with("creds", backend="requests")


# ---------------------------------------------------------------------------
# list_sheets
# ---------------------------------------------------------------------------


def test_list_sheets_returns_names() -> None:
    rest = make_mock_rest(
        meta_sheets=[
            {"properties": {"title": "Sheet1", "sheetId": 0}},
            {"properties": {"title": "Data", "sheetId": 1}},
        ]
    )
    sheets = make_sheets(rest)
    names = sheets.list_sheets(spreadsheet_id="sheet-id")
    assert names == ["Sheet1", "Data"]


def test_list_sheets_raises_on_missing_spreadsheet() -> None:
    rest = make_mock_rest()
    rest.get.side_effect = make_http_error(404)
    sheets = make_sheets(rest)
    with pytest.raises(GoogleError):
        sheets.list_sheets(spreadsheet_id="bad-id")


# ---------------------------------------------------------------------------
# add_sheet
# ---------------------------------------------------------------------------


def test_add_sheet_creates_worksheet() -> None:
    rest = make_mock_rest()
    sheets = make_sheets(rest)
    sheets.add_sheet("NewSheet", spreadsheet_id="sheet-id")
    url, kwargs = rest.post.call_args
    assert url[0] == f"{_SHEETS_BASE}/sheet-id:batchUpdate"
    assert kwargs["json"]["requests"][0]["addSheet"]["properties"]["title"] == "NewSheet"
    rest.put.assert_not_called()


def test_add_sheet_with_rows_writes_data() -> None:
    rest = make_mock_rest()
    sheets = make_sheets(rest)
    rows = [{"x": 1, "y": 2}]
    sheets.add_sheet("NewSheet", spreadsheet_id="sheet-id", rows=rows)
    _, kwargs = rest.put.call_args
    assert kwargs["json"] == {"values": [["x", "y"], [1, 2]]}
    assert sheets.rows is rows


# ---------------------------------------------------------------------------
# delete_sheet
# ---------------------------------------------------------------------------


def test_delete_sheet_sends_delete_request() -> None:
    rest = make_mock_rest()
    sheets = make_sheets(rest)
    sheets.delete_sheet("Sheet1", spreadsheet_id="sheet-id")
    _, kwargs = rest.post.call_args
    assert kwargs["json"]["requests"][0]["deleteSheet"]["sheetId"] == 0


def test_delete_sheet_raises_on_missing_sheet() -> None:
    rest = make_mock_rest()
    sheets = make_sheets(rest)
    with pytest.raises(GoogleError):
        sheets.delete_sheet("Nope", spreadsheet_id="sheet-id")


# ---------------------------------------------------------------------------
# share
# ---------------------------------------------------------------------------


def test_share_defaults_to_reader() -> None:
    rest = make_mock_rest()
    sheets = make_sheets(rest)
    sheets.share("alice@example.com", spreadsheet_id="sheet-id")
    url, kwargs = rest.post.call_args
    assert url[0] == f"{_DRIVE_BASE}/files/sheet-id/permissions"
    assert kwargs["params"] == {"sendNotificationEmail": "false"}
    assert kwargs["json"] == {"type": "user", "role": "reader", "emailAddress": "alice@example.com"}


def test_share_custom_role() -> None:
    rest = make_mock_rest()
    sheets = make_sheets(rest)
    sheets.share("bob@example.com", spreadsheet_id="sheet-id", role="writer")
    _, kwargs = rest.post.call_args
    assert kwargs["json"] == {"type": "user", "role": "writer", "emailAddress": "bob@example.com"}


# ---------------------------------------------------------------------------
# upsert_rows
# ---------------------------------------------------------------------------

_HEADERS = ["id", "name", "score"]
_DATA = [["1", "Alice", "95"], ["2", "Bob", "82"]]


def _upsert_rest(
    headers: list[str] = _HEADERS,
    data: list[list[str]] = _DATA,
) -> MagicMock:
    return make_mock_rest(values=[headers, *data])


def _batch_update_body(rest: MagicMock) -> dict[str, Any]:
    for call in rest.post.call_args_list:
        if call.args[0].endswith("values:batchUpdate"):
            return call.kwargs["json"]  # type: ignore[no-any-return]
    raise AssertionError("values:batchUpdate was not called")


def _append_calls(rest: MagicMock) -> list[Any]:
    return [c for c in rest.post.call_args_list if c.args[0].endswith(":append")]


def test_upsert_empty_sheet_writes_all() -> None:
    rest = make_mock_rest(values=[])
    rows = [{"id": "1", "name": "Alice"}]
    sheets = make_sheets(rest)
    count = sheets.upsert_rows(rows, key="id", spreadsheet_id="sheet-id", sheet_name="Sheet1")
    _, kwargs = rest.put.call_args
    assert kwargs["json"] == {"values": [["id", "name"], ["1", "Alice"]]}
    assert count == 1


def test_upsert_all_new_rows_appended() -> None:
    rest = _upsert_rest()
    rows = [{"id": "3", "name": "Carol", "score": "77"}]
    sheets = make_sheets(rest)
    count = sheets.upsert_rows(rows, key="id", spreadsheet_id="sheet-id", sheet_name="Sheet1")
    appends = _append_calls(rest)
    assert len(appends) == 1
    assert appends[0].kwargs["json"] == {"values": [["3", "Carol", "77"]]}
    assert count == 1


def test_upsert_patches_matching_row() -> None:
    rest = _upsert_rest()
    sheets = make_sheets(rest)
    sheets.upsert_rows(
        [{"id": "1", "score": "100"}], key="id", spreadsheet_id="sheet-id", sheet_name="Sheet1"
    )
    body = _batch_update_body(rest)
    assert body["data"] == [
        {"range": "'Sheet1'!A2", "values": [["1"]]},
        {"range": "'Sheet1'!C2", "values": [["100"]]},
    ]
    assert not _append_calls(rest)


def test_upsert_composite_key_matches() -> None:
    rest = make_mock_rest(
        values=[
            ["region", "id", "score"],
            ["us", "1", "95"],
            ["eu", "1", "80"],
        ]
    )
    rows = [{"region": "eu", "id": "1", "score": "99"}]
    sheets = make_sheets(rest)
    sheets.upsert_rows(rows, key=["region", "id"], spreadsheet_id="sheet-id", sheet_name="Sheet1")
    body = _batch_update_body(rest)
    assert body["data"] == [
        {"range": "'Sheet1'!A3", "values": [["eu"]]},
        {"range": "'Sheet1'!B3", "values": [["1"]]},
        {"range": "'Sheet1'!C3", "values": [["99"]]},
    ]


def test_upsert_on_conflict_update_all() -> None:
    rest = make_mock_rest(values=[["id", "score"], ["1", "95"], ["1", "82"]])
    sheets = make_sheets(rest)
    count = sheets.upsert_rows(
        [{"id": "1", "score": "99"}],
        key="id",
        spreadsheet_id="sheet-id",
        sheet_name="Sheet1",
        on_conflict="update_all",
    )
    body = _batch_update_body(rest)
    patched_rows = {u["range"][-1] for u in body["data"]}
    assert "2" in patched_rows and "3" in patched_rows
    assert count == 1


def test_upsert_on_conflict_update_first() -> None:
    rest = make_mock_rest(values=[["id", "v"], ["1", "a"], ["1", "b"]])
    sheets = make_sheets(rest)
    sheets.upsert_rows(
        [{"id": "1", "v": "z"}],
        key="id",
        spreadsheet_id="sheet-id",
        sheet_name="Sheet1",
        on_conflict="update_first",
    )
    body = _batch_update_body(rest)
    assert all("2" in u["range"] for u in body["data"])


def test_upsert_on_conflict_update_last() -> None:
    rest = make_mock_rest(values=[["id", "v"], ["1", "a"], ["1", "b"]])
    sheets = make_sheets(rest)
    sheets.upsert_rows(
        [{"id": "1", "v": "z"}],
        key="id",
        spreadsheet_id="sheet-id",
        sheet_name="Sheet1",
        on_conflict="update_last",
    )
    body = _batch_update_body(rest)
    assert all("3" in u["range"] for u in body["data"])


def test_upsert_on_conflict_raise() -> None:
    rest = make_mock_rest(values=[["id", "v"], ["1", "a"], ["1", "b"]])
    sheets = make_sheets(rest)
    with pytest.raises(GoogleError, match="Duplicate"):
        sheets.upsert_rows(
            [{"id": "1", "v": "z"}],
            key="id",
            spreadsheet_id="sheet-id",
            sheet_name="Sheet1",
            on_conflict="raise",
        )


def test_upsert_on_conflict_skip() -> None:
    rest = make_mock_rest(values=[["id", "v"], ["1", "a"], ["1", "b"]])
    sheets = make_sheets(rest)
    count = sheets.upsert_rows(
        [{"id": "1", "v": "z"}],
        key="id",
        spreadsheet_id="sheet-id",
        sheet_name="Sheet1",
        on_conflict="skip",
    )
    assert not any(c.args[0].endswith("values:batchUpdate") for c in rest.post.call_args_list)
    assert count == 0


def test_upsert_new_columns_added_to_header() -> None:
    rest = _upsert_rest()
    sheets = make_sheets(rest)
    sheets.upsert_rows(
        [{"id": "1", "score": "99", "grade": "A"}],
        key="id",
        spreadsheet_id="sheet-id",
        sheet_name="Sheet1",
    )
    _, kwargs = rest.put.call_args
    assert kwargs["json"] == {"values": [["id", "name", "score", "grade"]]}


def test_upsert_missing_key_column_raises() -> None:
    rest = _upsert_rest()
    sheets = make_sheets(rest)
    with pytest.raises(GoogleError, match="Key column"):
        sheets.upsert_rows(
            [{"bad_key": "1"}], key="bad_key", spreadsheet_id="sheet-id", sheet_name="Sheet1"
        )


def test_upsert_empty_rows_is_no_op() -> None:
    rest = make_mock_rest()
    sheets = make_sheets(rest)
    count = sheets.upsert_rows([], key="id", spreadsheet_id="sheet-id", sheet_name="Sheet1")
    assert count == 0
    rest.get.assert_not_called()


def test_upsert_sets_self_rows() -> None:
    rest = make_mock_rest(values=[])
    rows = [{"id": "1"}]
    sheets = make_sheets(rest)
    sheets.upsert_rows(rows, key="id", spreadsheet_id="sheet-id", sheet_name="Sheet1")
    assert sheets.rows is rows


# ---------------------------------------------------------------------------
# list[list] input — header auto-detection
# ---------------------------------------------------------------------------


def test_append_rows_list_input_matching_header_dropped() -> None:
    rest = make_mock_rest(values=[["name", "age"]])
    sheets = make_sheets(rest)
    count = sheets.append_rows(
        [["name", "age"], ["Alice", "30"]], spreadsheet_id="sheet-id", sheet_name="Sheet1"
    )
    appends = _append_calls(rest)
    assert len(appends) == 1
    assert appends[0].kwargs["json"] == {"values": [["Alice", "30"]]}
    assert count == 1


def test_append_rows_list_input_no_header_row() -> None:
    rest = make_mock_rest(values=[["name", "age"]])
    sheets = make_sheets(rest)
    count = sheets.append_rows(
        [["Alice", "30"], ["Bob", "25"]], spreadsheet_id="sheet-id", sheet_name="Sheet1"
    )
    appends = _append_calls(rest)
    assert appends[0].kwargs["json"] == {"values": [["Alice", "30"], ["Bob", "25"]]}
    assert count == 2


def test_append_rows_list_input_empty_sheet_writes_header_and_data_in_one_call() -> None:
    rest = make_mock_rest(values=[])
    sheets = make_sheets(rest)
    sheets.append_rows(
        [["name", "age"], ["Alice", "30"]], spreadsheet_id="sheet-id", sheet_name="Sheet1"
    )
    _, kwargs = rest.put.call_args
    assert kwargs["json"] == {"values": [["name", "age"], ["Alice", "30"]]}
    assert not _append_calls(rest)


def test_update_rows_list_input_first_row_becomes_headers() -> None:
    rest = make_mock_rest()
    sheets = make_sheets(rest)
    count = sheets.update_rows([["x", "y"], [1, 2]], spreadsheet_id="sheet-id", sheet_name="Sheet1")
    _, kwargs = rest.put.call_args
    assert kwargs["json"] == {"values": [["x", "y"], [1, 2]]}
    assert count == 1


def test_upsert_rows_list_input_matching_header_dropped() -> None:
    rest = _upsert_rest()
    sheets = make_sheets(rest)
    count = sheets.upsert_rows(
        [["id", "name", "score"], ["3", "Carol", "77"]],
        key="id",
        spreadsheet_id="sheet-id",
        sheet_name="Sheet1",
    )
    assert len(_append_calls(rest)) == 1
    assert count == 1


def test_upsert_rows_list_input_no_header_row() -> None:
    rest = _upsert_rest()
    sheets = make_sheets(rest)
    count = sheets.upsert_rows(
        [["3", "Carol", "77"]], key="id", spreadsheet_id="sheet-id", sheet_name="Sheet1"
    )
    assert len(_append_calls(rest)) == 1
    assert count == 1


def test_upsert_rows_list_input_empty_sheet() -> None:
    rest = make_mock_rest(values=[])
    sheets = make_sheets(rest)
    count = sheets.upsert_rows(
        [["id", "name"], ["1", "Alice"]],
        key="id",
        spreadsheet_id="sheet-id",
        sheet_name="Sheet1",
    )
    _, kwargs = rest.put.call_args
    assert kwargs["json"] == {"values": [["id", "name"], ["1", "Alice"]]}
    assert count == 1


def test_add_sheet_list_input() -> None:
    rest = make_mock_rest()
    sheets = make_sheets(rest)
    sheets.add_sheet("NewSheet", spreadsheet_id="sheet-id", rows=[["x", "y"], [1, 2]])
    _, kwargs = rest.put.call_args
    assert kwargs["json"] == {"values": [["x", "y"], [1, 2]]}


def test_create_list_input() -> None:
    rest = make_mock_rest()
    sheets = make_sheets(rest)
    sheets.create("My Sheet", rows=[["col"], ["val"]])
    _, kwargs = rest.put.call_args
    assert kwargs["json"] == {"values": [["col"], ["val"]]}


# ---------------------------------------------------------------------------
# rest client caching
# ---------------------------------------------------------------------------


def test_rest_client_is_built_once() -> None:
    mock_rest = make_mock_rest(values=[])
    with (
        patch("tha_google_runner.sheets.build_credentials", return_value="creds") as mock_build,
        patch("tha_google_runner.sheets.RestClient", return_value=mock_rest) as mock_rest_cls,
    ):
        sheets = ThaSheets()
        sheets.read(spreadsheet_id="sheet-id", sheet_name="Sheet1")
        sheets.read(spreadsheet_id="sheet-id", sheet_name="Sheet1")
    assert mock_build.call_count == 1
    assert mock_rest_cls.call_count == 1
