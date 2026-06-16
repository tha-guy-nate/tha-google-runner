import io
from unittest.mock import MagicMock, patch

import pytest

from tha_google_runner.drive import ThaDrive
from tha_google_runner.errors import GoogleError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_drive(files: list | None = None) -> tuple[ThaDrive, MagicMock]:
    svc = MagicMock()
    svc.files().list().execute.return_value = {"files": files or [], "nextPageToken": None}
    svc.files().get().execute.return_value = {"id": "f1", "name": "test.pdf"}
    drive = ThaDrive()
    drive._service = svc
    return drive, svc


def _mock_downloader(content: bytes) -> MagicMock:
    buf_holder: list[io.BytesIO] = []

    def fake_download(buf: io.BytesIO, request: object) -> MagicMock:
        buf_holder.append(buf)
        dl = MagicMock()
        call_count = 0

        def next_chunk() -> tuple[MagicMock, bool]:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                buf.write(content)
                return MagicMock(), True
            return MagicMock(), True

        dl.next_chunk.side_effect = next_chunk
        return dl

    return fake_download


# ---------------------------------------------------------------------------
# _resolve_id
# ---------------------------------------------------------------------------


def test_resolve_id_accepts_raw_id() -> None:
    drive, svc = make_drive()
    drive.get(file_id="abc123")
    svc.files().get.assert_called_with(fileId="abc123", fields="*")


def test_resolve_id_accepts_full_url() -> None:
    drive, svc = make_drive()
    drive.get(url="https://drive.google.com/file/d/abc123/view")
    svc.files().get.assert_called_with(fileId="abc123", fields="*")


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
    drive, svc = make_drive()
    drive.list_files()
    call_kwargs = svc.files().list.call_args[1]
    assert "trashed = false" in call_kwargs["q"]


def test_list_files_adds_folder_filter() -> None:
    drive, svc = make_drive()
    drive.list_files(folder_id="folder-abc")
    call_kwargs = svc.files().list.call_args[1]
    assert "'folder-abc' in parents" in call_kwargs["q"]


def test_list_files_adds_custom_query() -> None:
    drive, svc = make_drive()
    drive.list_files(query="mimeType = 'application/pdf'")
    call_kwargs = svc.files().list.call_args[1]
    assert "mimeType = 'application/pdf'" in call_kwargs["q"]


def test_list_files_paginates() -> None:
    svc = MagicMock()
    svc.files().list().execute.side_effect = [
        {"files": [{"id": "1"}], "nextPageToken": "tok"},
        {"files": [{"id": "2"}], "nextPageToken": None},
    ]
    drive = ThaDrive()
    drive._service = svc
    result = drive.list_files()
    assert [f["id"] for f in result] == ["1", "2"]


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------


def test_search_contains_by_default() -> None:
    drive, svc = make_drive()
    drive.search("report")
    call_kwargs = svc.files().list.call_args[1]
    assert "name contains 'report'" in call_kwargs["q"]


def test_search_exact_uses_equals() -> None:
    drive, svc = make_drive()
    drive.search("report.csv", exact=True)
    call_kwargs = svc.files().list.call_args[1]
    assert "name = 'report.csv'" in call_kwargs["q"]


def test_search_escapes_single_quotes() -> None:
    drive, svc = make_drive()
    drive.search("it's a file")
    call_kwargs = svc.files().list.call_args[1]
    assert "it\\'s a file" in call_kwargs["q"]


# ---------------------------------------------------------------------------
# download
# ---------------------------------------------------------------------------


def test_download_returns_bytes() -> None:
    content = b"PDF content here"
    drive, svc = make_drive()

    with patch("googleapiclient.http.MediaIoBaseDownload", side_effect=_mock_downloader(content)):
        result = drive.download(file_id="f1")

    svc.files().get_media.assert_called_with(fileId="f1")
    assert result == content


def test_download_accepts_url() -> None:
    content = b"data"
    drive, svc = make_drive()

    with patch("googleapiclient.http.MediaIoBaseDownload", side_effect=_mock_downloader(content)):
        drive.download(url="https://drive.google.com/file/d/xyz/view")

    svc.files().get_media.assert_called_with(fileId="xyz")


def test_download_raises_without_id_or_url() -> None:
    drive, _ = make_drive()
    with pytest.raises(GoogleError, match="Provide either"):
        drive.download()
