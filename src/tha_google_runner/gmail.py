from __future__ import annotations

import base64
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, ClassVar

from tha_google_runner.auth import SCOPE_GMAIL_READONLY, SCOPE_GMAIL_SEND, build_credentials
from tha_google_runner.errors import GoogleError


def _join_addresses(value: str | list[str]) -> str:
    return ", ".join(value) if isinstance(value, list) else value


def _decode_part(data: str) -> str:
    return base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")


def _extract_body(payload: dict[str, Any]) -> str:
    mime = payload.get("mimeType", "")
    if mime in ("text/plain", "text/html"):
        data = payload.get("body", {}).get("data", "")
        return _decode_part(data) if data else ""

    parts = payload.get("parts", [])
    # prefer text/plain; fall back to first available
    plain = next((p for p in parts if p.get("mimeType") == "text/plain"), None)
    if plain:
        return _extract_body(plain)
    for part in parts:
        body = _extract_body(part)
        if body:
            return body
    return ""


def _header(message: dict[str, Any], name: str) -> str:
    for h in message.get("payload", {}).get("headers", []):
        if h["name"].lower() == name.lower():
            return str(h["value"])
    return ""


class ThaGmail:
    _SCOPES: ClassVar[list[str]] = [SCOPE_GMAIL_SEND, SCOPE_GMAIL_READONLY]

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

    def _get_service(self) -> Any:
        if self._service is None:
            from googleapiclient.discovery import build

            creds = build_credentials(self._credentials_file, self._token_file, self._scopes)
            self._service = build("gmail", "v1", credentials=creds)
        return self._service

    def send(
        self,
        *,
        to: str | list[str],
        subject: str,
        body: str,
        cc: str | list[str] | None = None,
        bcc: str | list[str] | None = None,
        html: bool = False,
    ) -> dict[str, Any]:
        if html:
            msg: MIMEText | MIMEMultipart = MIMEMultipart("alternative")
            msg.attach(MIMEText(body, "html"))
        else:
            msg = MIMEText(body, "plain")

        msg["to"] = _join_addresses(to)
        msg["subject"] = subject
        if cc:
            msg["cc"] = _join_addresses(cc)
        if bcc:
            msg["bcc"] = _join_addresses(bcc)

        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        return self._get_service().users().messages().send(userId="me", body={"raw": raw}).execute()  # type: ignore[no-any-return]

    def list_messages(
        self,
        *,
        query: str | None = None,
        max_results: int = 100,
    ) -> list[dict[str, Any]]:
        svc = self._get_service()
        results: list[dict[str, Any]] = []
        page_token: str | None = None

        while len(results) < max_results:
            kwargs: dict[str, Any] = {
                "userId": "me",
                "maxResults": min(500, max_results - len(results)),
            }
            if query:
                kwargs["q"] = query
            if page_token:
                kwargs["pageToken"] = page_token

            response = svc.users().messages().list(**kwargs).execute()
            results.extend(response.get("messages", []))
            page_token = response.get("nextPageToken")
            if not page_token:
                break

        return results[:max_results]

    def read(self, *, message_id: str) -> dict[str, Any]:
        message = (
            self._get_service()
            .users()
            .messages()
            .get(userId="me", id=message_id, format="full")
            .execute()
        )
        if not message:
            raise GoogleError(f"Message not found: {message_id}")

        return {
            "id": message.get("id", ""),
            "thread_id": message.get("threadId", ""),
            "subject": _header(message, "subject"),
            "from_": _header(message, "from"),
            "to": _header(message, "to"),
            "date": _header(message, "date"),
            "body": _extract_body(message.get("payload", {})),
        }
