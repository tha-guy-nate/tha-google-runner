from __future__ import annotations

import re
from typing import Any

from tha_google_runner.auth import build_credentials
from tha_google_runner.errors import GoogleError

_ID_RE = re.compile(r"/d/([a-zA-Z0-9_-]+)|[?&]id=([a-zA-Z0-9_-]+)")

_TITLE_TYPES = {"TITLE", "CENTERED_TITLE"}
_BODY_TYPES = {"BODY", "SUBTITLE"}


def _extract_text(text_obj: dict[str, Any] | None) -> str:
    if not text_obj:
        return ""
    parts: list[str] = []
    for el in text_obj.get("textElements", []):
        if "textRun" in el:
            parts.append(el["textRun"]["content"])
    return "".join(parts).strip()


class ThaSlides:
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
            self._service = build("slides", "v1", credentials=creds)
        return self._service

    def _resolve_id(self, presentation_id: str | None, url: str | None) -> str:
        if url is not None:
            m = _ID_RE.search(url)
            if not m:
                raise GoogleError(f"Could not parse presentation ID from URL: {url}")
            result = m.group(1) or m.group(2)
            if result is None:
                raise GoogleError(f"Could not parse presentation ID from URL: {url}")
            return result
        if presentation_id is not None:
            return presentation_id
        raise GoogleError("Provide either presentation_id= or url=")

    def read(
        self,
        *,
        presentation_id: str | None = None,
        url: str | None = None,
    ) -> list[dict[str, Any]]:
        pid = self._resolve_id(presentation_id, url)
        presentation = self._get_service().presentations().get(presentationId=pid).execute()

        results: list[dict[str, Any]] = []
        for index, slide in enumerate(presentation.get("slides", [])):
            title = ""
            body_parts: list[str] = []

            for el in slide.get("pageElements", []):
                shape = el.get("shape", {})
                p_type = shape.get("placeholder", {}).get("type", "")
                text = _extract_text(shape.get("text"))
                if p_type in _TITLE_TYPES:
                    title = text
                elif p_type in _BODY_TYPES and text:
                    body_parts.append(text)

            notes = ""
            notes_page = slide.get("slideProperties", {}).get("notesPage", {})
            for el in notes_page.get("pageElements", []):
                shape = el.get("shape", {})
                if shape.get("placeholder", {}).get("type") == "BODY":
                    notes = _extract_text(shape.get("text"))
                    break

            results.append(
                {
                    "index": index,
                    "object_id": slide.get("objectId", ""),
                    "title": title,
                    "body": "\n".join(body_parts),
                    "notes": notes,
                }
            )
        return results

    def get(
        self,
        *,
        presentation_id: str | None = None,
        url: str | None = None,
    ) -> dict[str, Any]:
        pid = self._resolve_id(presentation_id, url)
        return self._get_service().presentations().get(presentationId=pid).execute()  # type: ignore[no-any-return]
