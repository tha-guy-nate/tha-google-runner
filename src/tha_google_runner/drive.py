from __future__ import annotations

import re
from typing import Any, ClassVar, Literal

from tha_google_runner._rest import RestClient
from tha_google_runner.auth import SCOPE_DRIVE_READONLY, build_credentials
from tha_google_runner.errors import GoogleError

_ID_RE = re.compile(r"/d/([a-zA-Z0-9_-]+)|[?&]id=([a-zA-Z0-9_-]+)")

_DEFAULT_FIELDS = "id,name,mimeType,modifiedTime,size"
_DRIVE_BASE = "https://www.googleapis.com/drive/v3"


class ThaDrive:
    _SCOPES: ClassVar[list[str]] = [SCOPE_DRIVE_READONLY]

    def __init__(
        self,
        *,
        credentials_file: str | None = None,
        token_file: str | None = None,
        scopes: list[str] | None = None,
        backend: Literal["requests", "httpx"] = "requests",
    ) -> None:
        self._credentials_file = credentials_file
        self._token_file = token_file
        self._scopes = scopes if scopes is not None else self._SCOPES
        self._backend = backend
        self._rest: RestClient | None = None

    def _get_rest(self) -> RestClient:
        if self._rest is None:
            creds = build_credentials(self._credentials_file, self._token_file, self._scopes)
            self._rest = RestClient(creds, backend=self._backend)
        return self._rest

    def _resolve_id(self, file_id: str | None, url: str | None) -> str:
        if url is not None:
            m = _ID_RE.search(url)
            if not m:
                raise GoogleError(f"Could not parse file ID from URL: {url}")
            result = m.group(1) or m.group(2)
            if result is None:  # pragma: no cover — unreachable, both alternatives require 1+ chars
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
        rest = self._get_rest()
        q_parts: list[str] = ["trashed = false"]
        if folder_id:
            q_parts.append(f"'{folder_id}' in parents")
        if query:
            q_parts.append(query)
        q = " and ".join(q_parts)

        results: list[dict[str, Any]] = []
        page_token: str | None = None
        while True:
            params: dict[str, Any] = {
                "q": q,
                "fields": f"nextPageToken,files({fields})",
                "pageSize": 1000,
            }
            if page_token:
                params["pageToken"] = page_token
            response = rest.get(f"{_DRIVE_BASE}/files", params=params)
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
        return self._get_rest().get(  # type: ignore[no-any-return]
            f"{_DRIVE_BASE}/files/{fid}", params={"fields": fields}
        )

    def export(
        self,
        *,
        file_id: str | None = None,
        url: str | None = None,
        mime_type: str = "text/plain",
    ) -> bytes:
        fid = self._resolve_id(file_id, url)
        return self._get_rest().download(
            f"{_DRIVE_BASE}/files/{fid}/export", params={"mimeType": mime_type}
        )

    def download(
        self,
        *,
        file_id: str | None = None,
        url: str | None = None,
    ) -> bytes:
        fid = self._resolve_id(file_id, url)
        return self._get_rest().download(f"{_DRIVE_BASE}/files/{fid}", params={"alt": "media"})
