from __future__ import annotations

import re
from typing import Any

from tha_google_runner.auth import build_credentials
from tha_google_runner.errors import GoogleError, with_retry

_ID_RE = re.compile(r"/d/([a-zA-Z0-9_-]+)|[?&]id=([a-zA-Z0-9_-]+)")

_DEFAULT_FIELDS = "id,name,mimeType,modifiedTime,size"


class ThaDrive:
    def __init__(
        self,
        *,
        credentials_file: str | None = None,
        token_file: str | None = None,
    ) -> None:
        self._credentials_file = credentials_file
        self._token_file = token_file
        self._service: Any = None

    def _get_service(self) -> Any:
        if self._service is None:
            from googleapiclient.discovery import build

            creds = build_credentials(self._credentials_file, self._token_file)
            self._service = build("drive", "v3", credentials=creds)
        return self._service

    def _resolve_id(self, file_id: str | None, url: str | None) -> str:
        if url is not None:
            m = _ID_RE.search(url)
            if not m:
                raise GoogleError(f"Could not parse file ID from URL: {url}")
            result = m.group(1) or m.group(2)
            if result is None:
                raise GoogleError(f"Could not parse file ID from URL: {url}")
            return result
        if file_id is not None:
            return file_id
        raise GoogleError("Provide either file_id= or url=")

    def list_files(
        self,
        *,
        query: str | None = None,
        folder_id: str | None = None,
        fields: str = _DEFAULT_FIELDS,
    ) -> list[dict[str, Any]]:
        service = self._get_service()
        q_parts: list[str] = ["trashed = false"]
        if folder_id:
            q_parts.append(f"'{folder_id}' in parents")
        if query:
            q_parts.append(query)
        q = " and ".join(q_parts)

        results: list[dict[str, Any]] = []
        page_token: str | None = None
        while True:
            kwargs: dict[str, Any] = {
                "q": q,
                "fields": f"nextPageToken,files({fields})",
                "pageSize": 1000,
            }
            if page_token:
                kwargs["pageToken"] = page_token
            response = with_retry(lambda: service.files().list(**kwargs).execute())
            results.extend(response.get("files", []))
            page_token = response.get("nextPageToken")
            if not page_token:
                break
        return results

    def search(
        self,
        name: str,
        *,
        folder_id: str | None = None,
        exact: bool = False,
    ) -> list[dict[str, Any]]:
        escaped = name.replace("'", "\\'")
        op = "=" if exact else "contains"
        return self.list_files(query=f"name {op} '{escaped}'", folder_id=folder_id)

    def get(
        self,
        *,
        file_id: str | None = None,
        url: str | None = None,
        fields: str = "*",
    ) -> dict[str, Any]:
        fid = self._resolve_id(file_id, url)
        return with_retry(lambda: self._get_service().files().get(fileId=fid, fields=fields).execute())  # type: ignore[no-any-return]

    def export(
        self,
        *,
        file_id: str | None = None,
        url: str | None = None,
        mime_type: str = "text/plain",
    ) -> bytes:
        import io

        from googleapiclient.http import MediaIoBaseDownload

        fid = self._resolve_id(file_id, url)
        request = self._get_service().files().export_media(fileId=fid, mimeType=mime_type)
        buf = io.BytesIO()
        downloader = MediaIoBaseDownload(buf, request)
        done = False
        while not done:
            _, done = with_retry(downloader.next_chunk)
        return buf.getvalue()

    def download(
        self,
        *,
        file_id: str | None = None,
        url: str | None = None,
    ) -> bytes:
        import io

        from googleapiclient.http import MediaIoBaseDownload

        fid = self._resolve_id(file_id, url)
        request = self._get_service().files().get_media(fileId=fid)
        buf = io.BytesIO()
        downloader = MediaIoBaseDownload(buf, request)
        done = False
        while not done:
            _, done = with_retry(downloader.next_chunk)
        return buf.getvalue()
