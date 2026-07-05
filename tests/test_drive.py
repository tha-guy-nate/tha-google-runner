from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from tha_google_runner.drive import _DRIVE_BASE, ThaDrive
from tha_google_runner.errors import GoogleError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_drive(files: list[dict[str, Any]] | None = None) -> tuple[ThaDrive, MagicMock]:
    rest = MagicMock()
    rest.get.return_value = {"files": files or [], "nextPageToken": None}
    drive = ThaDrive()
    drive._rest = rest
    return drive, rest


# ---------------------------------------------------------------------------
# _get_rest
# ---------------------------------------------------------------------------


def test_get_rest_builds_and_caches_lazily() -> None:
    drive = ThaDrive(credentials_file="secret.json", token_file="token.json")
    mock_rest = MagicMock()
    mock_rest.get.return_value = {"id": "f1"}

    with (
        patch("tha_google_runner.drive.build_credentials") as mock_build_creds,
        patch("tha_google_runner.drive.RestClient") as mock_rest_cls,
    ):
        mock_build_creds.return_value = "creds"
        mock_rest_cls.return_value = mock_rest
        drive.get(file_id="f1")
        drive.get(file_id="f1")

    mock_build_creds.assert_called_once_with("secret.json", "token.json", drive._scopes)
    mock_rest_cls.assert_called_once_with("creds", backend="requests")


# ---------------------------------------------------------------------------
# _resolve_id
# ---------------------------------------------------------------------------


def test_resolve_id_accepts_raw_id() -> None:
    drive, rest = make_drive()
    rest.get.return_value = {"id": "abc123"}
    drive.get(file_id="abc123")
    rest.get.assert_called_with(f"{_DRIVE_BASE}/files/abc123", params={"fields": "*"})


def test_resolve_id_accepts_full_url() -> None:
    drive, rest = make_drive()
    rest.get.return_value = {"id": "abc123"}
    drive.get(url="https://drive.google.com/file/d/abc123/view")
    rest.get.assert_called_with(f"{_DRIVE_BASE}/files/abc123", params={"fields": "*"})


def test_resolve_id_raises_on_invalid_url() -> None:
    drive, _ = make_drive()
    with pytest.raises(GoogleError, match="Could not parse"):
        drive.get(url="https://notgoogle.com/foo")


def test_resolve_id_raises_when_neither_provided() -> None:
    drive, _ = make_drive()
    with pytest.raises(GoogleError, match="Provide either"):
        drive.get()


# ---------------------------------------------------------------------------
# list_files
# ---------------------------------------------------------------------------


def test_list_files_returns_files() -> None:
    files = [{"id": "1", "name": "a.csv"}, {"id": "2", "name": "b.csv"}]
    drive, _ = make_drive(files)
    result = drive.list_files()
    assert result == files


def test_list_files_filters_trashed() -> None:
    drive, rest = make_drive()
    drive.list_files()
    _, kwargs = rest.get.call_args
    assert "trashed = false" in kwargs["params"]["q"]


def test_list_files_adds_folder_filter() -> None:
    drive, rest = make_drive()
    drive.list_files(folder_id="folder-abc")
    _, kwargs = rest.get.call_args
    assert "'folder-abc' in parents" in kwargs["params"]["q"]


def test_list_files_adds_custom_query() -> None:
    drive, rest = make_drive()
    drive.list_files(query="mimeType = 'application/pdf'")
    _, kwargs = rest.get.call_args
    assert "mimeType = 'application/pdf'" in kwargs["params"]["q"]


def test_list_files_paginates() -> None:
    rest = MagicMock()
    rest.get.side_effect = [
        {"files": [{"id": "1"}], "nextPageToken": "tok"},
        {"files": [{"id": "2"}], "nextPageToken": None},
    ]
    drive = ThaDrive()
    drive._rest = rest
    result = drive.list_files()
    assert [f["id"] for f in result] == ["1", "2"]


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------


def test_search_contains_by_default() -> None:
    drive, rest = make_drive()
    drive.search("report")
    _, kwargs = rest.get.call_args
    assert "name contains 'report'" in kwargs["params"]["q"]


def test_search_exact_uses_equals() -> None:
    drive, rest = make_drive()
    drive.search("report.csv", exact=True)
    _, kwargs = rest.get.call_args
    assert "name = 'report.csv'" in kwargs["params"]["q"]


def test_search_escapes_single_quotes() -> None:
    drive, rest = make_drive()
    drive.search("it's a file")
    _, kwargs = rest.get.call_args
    assert "it\\'s a file" in kwargs["params"]["q"]


# ---------------------------------------------------------------------------
# export
# ---------------------------------------------------------------------------


def test_export_returns_bytes() -> None:
    content = b"exported text content"
    drive, rest = make_drive()
    rest.download.return_value = content

    result = drive.export(file_id="f1", mime_type="text/plain")

    rest.download.assert_called_with(
        f"{_DRIVE_BASE}/files/f1/export", params={"mimeType": "text/plain"}
    )
    assert result == content


def test_export_accepts_url() -> None:
    drive, rest = make_drive()
    rest.download.return_value = b"data"

    drive.export(url="https://drive.google.com/file/d/xyz/view")

    rest.download.assert_called_with(
        f"{_DRIVE_BASE}/files/xyz/export", params={"mimeType": "text/plain"}
    )


# ---------------------------------------------------------------------------
# download
# ---------------------------------------------------------------------------


def test_download_returns_bytes() -> None:
    content = b"PDF content here"
    drive, rest = make_drive()
    rest.download.return_value = content

    result = drive.download(file_id="f1")

    rest.download.assert_called_with(f"{_DRIVE_BASE}/files/f1", params={"alt": "media"})
    assert result == content


def test_download_accepts_url() -> None:
    drive, rest = make_drive()
    rest.download.return_value = b"data"

    drive.download(url="https://drive.google.com/file/d/xyz/view")

    rest.download.assert_called_with(f"{_DRIVE_BASE}/files/xyz", params={"alt": "media"})


def test_download_raises_without_id_or_url() -> None:
    drive, _ = make_drive()
    with pytest.raises(GoogleError, match="Provide either"):
        drive.download()
