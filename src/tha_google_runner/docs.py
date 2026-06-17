from __future__ import annotations

import re
from typing import Any, ClassVar

from tha_google_runner.auth import SCOPE_DOCUMENTS, build_credentials
from tha_google_runner.errors import GoogleError, with_retry

_URL_RE = re.compile(r"/document/d/([a-zA-Z0-9_-]+)")


class ThaDocs:
    _SCOPES: ClassVar[list[str]] = [SCOPE_DOCUMENTS]

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
        self.content: str = ""

    def _get_service(self) -> Any:
        if self._service is None:
            from googleapiclient.discovery import build

            creds = build_credentials(self._credentials_file, self._token_file, self._scopes)
            self._service = build("docs", "v1", credentials=creds)
        return self._service

    def _resolve_id(self, doc_id: str | None, url: str | None) -> str:
        if url is not None:
            m = _URL_RE.search(url)
            if not m:
                raise GoogleError(f"Could not parse document ID from URL: {url}")
            return m.group(1)
        if doc_id is not None:
            return doc_id
        raise GoogleError("Provide either doc_id= or url=")

    def read(
        self,
        *,
        doc_id: str | None = None,
        url: str | None = None,
    ) -> str:
        did = self._resolve_id(doc_id, url)
        doc = with_retry(lambda: self._get_service().documents().get(documentId=did).execute())
        self.content = _extract_text(doc)
        return self.content

    def append(
        self,
        text: str,
        *,
        doc_id: str | None = None,
        url: str | None = None,
    ) -> None:
        did = self._resolve_id(doc_id, url)
        service = self._get_service()
        doc = with_retry(lambda: service.documents().get(documentId=did).execute())
        end_index = doc["body"]["content"][-1]["endIndex"] - 1
        with_retry(
            lambda: (
                service.documents()
                .batchUpdate(
                    documentId=did,
                    body={
                        "requests": [
                            {"insertText": {"location": {"index": end_index}, "text": text}}
                        ]
                    },
                )
                .execute()
            )
        )

    def insert_after(
        self,
        text: str,
        *,
        after: str,
        doc_id: str | None = None,
        url: str | None = None,
    ) -> None:
        did = self._resolve_id(doc_id, url)
        service = self._get_service()
        doc = with_retry(lambda: service.documents().get(documentId=did).execute())
        runs = _text_runs(doc)
        plain = "".join(t for _, t in runs)
        pos = plain.find(after)
        if pos == -1:
            raise GoogleError(f"String not found in document: {after!r}")
        insert_index = _map_char_to_index(runs, pos + len(after))
        with_retry(
            lambda: (
                service.documents()
                .batchUpdate(
                    documentId=did,
                    body={
                        "requests": [
                            {"insertText": {"location": {"index": insert_index}, "text": text}}
                        ]
                    },
                )
                .execute()
            )
        )

    def replace(
        self,
        *,
        old_text: str,
        new_text: str,
        doc_id: str | None = None,
        url: str | None = None,
        match_case: bool = True,
    ) -> int:
        did = self._resolve_id(doc_id, url)
        result = with_retry(
            lambda: (
                self._get_service()
                .documents()
                .batchUpdate(
                    documentId=did,
                    body={
                        "requests": [
                            {
                                "replaceAllText": {
                                    "containsText": {"text": old_text, "matchCase": match_case},
                                    "replaceText": new_text,
                                }
                            }
                        ]
                    },
                )
                .execute()
            )
        )
        replies = result.get("replies", [{}])
        return replies[0].get("replaceAllText", {}).get("occurrencesChanged", 0) if replies else 0


def _text_runs(doc: dict[str, Any]) -> list[tuple[int, str]]:
    runs: list[tuple[int, str]] = []
    for elem in doc.get("body", {}).get("content", []):
        paragraph = elem.get("paragraph")
        if paragraph:
            for pe in paragraph.get("elements", []):
                tr = pe.get("textRun")
                if tr and tr.get("content"):
                    runs.append((pe["startIndex"], tr["content"]))
    return runs


def _extract_text(doc: dict[str, Any]) -> str:
    return "".join(t for _, t in _text_runs(doc))


def _map_char_to_index(runs: list[tuple[int, str]], char_pos: int) -> int:
    """Map a plain-text character offset to a Docs API structural index."""
    offset = 0
    for start_index, text in runs:
        run_len = len(text)
        if offset + run_len > char_pos:
            return start_index + (char_pos - offset)
        offset += run_len
    if runs:
        last_start, last_text = runs[-1]
        return last_start + len(last_text)
    return 1
