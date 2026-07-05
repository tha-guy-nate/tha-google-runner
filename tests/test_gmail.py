import base64
from email import message_from_bytes
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from tha_google_runner.errors import GoogleError
from tha_google_runner.gmail import _GMAIL_BASE, ThaGmail

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_gmail() -> tuple[ThaGmail, MagicMock]:
    rest = MagicMock()
    g = ThaGmail()
    g._rest = rest
    return g, rest


def _b64(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).decode()


def _message(
    subject: str = "Hello",
    from_: str = "sender@example.com",
    to: str = "recipient@example.com",
    date: str = "Mon, 1 Jan 2024 00:00:00 +0000",
    body: str = "Message body",
    mime: str = "text/plain",
    message_id: str = "msg1",
    thread_id: str = "thread1",
) -> dict[str, Any]:
    return {
        "id": message_id,
        "threadId": thread_id,
        "payload": {
            "mimeType": mime,
            "headers": [
                {"name": "Subject", "value": subject},
                {"name": "From", "value": from_},
                {"name": "To", "value": to},
                {"name": "Date", "value": date},
            ],
            "body": {"data": _b64(body)},
        },
    }


# ---------------------------------------------------------------------------
# send
# ---------------------------------------------------------------------------


def test_send_calls_api() -> None:
    g, rest = make_gmail()
    rest.post.return_value = {"id": "sent1"}

    result = g.send(to="a@example.com", subject="Hi", body="Hello")

    assert result == {"id": "sent1"}
    args, kwargs = rest.post.call_args
    assert args[0] == f"{_GMAIL_BASE}/messages/send"
    raw = base64.urlsafe_b64decode(kwargs["json"]["raw"] + "==")
    parsed = message_from_bytes(raw)
    assert parsed["to"] == "a@example.com"
    assert parsed["subject"] == "Hi"


def test_send_list_of_recipients() -> None:
    g, rest = make_gmail()
    rest.post.return_value = {"id": "sent1"}

    g.send(to=["a@example.com", "b@example.com"], subject="Hi", body="Hello")

    _, kwargs = rest.post.call_args
    raw = base64.urlsafe_b64decode(kwargs["json"]["raw"] + "==")
    parsed = message_from_bytes(raw)
    assert "a@example.com" in parsed["to"]
    assert "b@example.com" in parsed["to"]


def test_send_with_cc_and_bcc() -> None:
    g, rest = make_gmail()
    rest.post.return_value = {"id": "s1"}

    g.send(to="a@example.com", subject="Hi", body="Hello", cc="c@example.com", bcc="b@example.com")

    _, kwargs = rest.post.call_args
    raw = base64.urlsafe_b64decode(kwargs["json"]["raw"] + "==")
    parsed = message_from_bytes(raw)
    assert parsed["cc"] == "c@example.com"
    assert parsed["bcc"] == "b@example.com"


def test_send_html_uses_multipart() -> None:
    g, rest = make_gmail()
    rest.post.return_value = {"id": "s1"}

    g.send(to="a@example.com", subject="Hi", body="<b>Hello</b>", html=True)

    _, kwargs = rest.post.call_args
    raw = base64.urlsafe_b64decode(kwargs["json"]["raw"] + "==")
    parsed = message_from_bytes(raw)
    assert parsed.get_content_type() == "multipart/alternative"


# ---------------------------------------------------------------------------
# list_messages
# ---------------------------------------------------------------------------


def test_list_messages_returns_messages() -> None:
    g, rest = make_gmail()
    msgs = [{"id": "1", "threadId": "t1"}, {"id": "2", "threadId": "t2"}]
    rest.get.return_value = {"messages": msgs, "nextPageToken": None}

    result = g.list_messages()
    assert result == msgs


def test_list_messages_passes_query() -> None:
    g, rest = make_gmail()
    rest.get.return_value = {"messages": [], "nextPageToken": None}

    g.list_messages(query="from:boss@example.com")

    _, kwargs = rest.get.call_args
    assert kwargs["params"]["q"] == "from:boss@example.com"


def test_list_messages_paginates() -> None:
    g, rest = make_gmail()
    rest.get.side_effect = [
        {"messages": [{"id": "1"}], "nextPageToken": "tok"},
        {"messages": [{"id": "2"}], "nextPageToken": None},
    ]

    result = g.list_messages()
    assert [m["id"] for m in result] == ["1", "2"]


def test_list_messages_respects_max_results() -> None:
    g, rest = make_gmail()
    msgs = [{"id": str(i)} for i in range(10)]
    rest.get.return_value = {"messages": msgs, "nextPageToken": None}

    result = g.list_messages(max_results=3)
    assert len(result) == 3


# ---------------------------------------------------------------------------
# read
# ---------------------------------------------------------------------------


def test_read_returns_parsed_message() -> None:
    g, rest = make_gmail()
    rest.get.return_value = _message(
        subject="Test Subject",
        from_="sender@example.com",
        to="me@example.com",
        body="Hello there",
    )

    result = g.read(message_id="msg1")

    assert result["subject"] == "Test Subject"
    assert result["from_"] == "sender@example.com"
    assert result["to"] == "me@example.com"
    assert result["body"] == "Hello there"
    assert result["id"] == "msg1"
    assert result["thread_id"] == "thread1"


def test_read_multipart_prefers_plain_text() -> None:
    g, rest = make_gmail()
    message = {
        "id": "m1",
        "threadId": "t1",
        "payload": {
            "mimeType": "multipart/alternative",
            "headers": [],
            "parts": [
                {"mimeType": "text/plain", "body": {"data": _b64("plain text")}},
                {"mimeType": "text/html", "body": {"data": _b64("<b>html</b>")}},
            ],
        },
    }
    rest.get.return_value = message

    result = g.read(message_id="m1")
    assert result["body"] == "plain text"


def test_read_multipart_falls_back_to_first_nonempty_part() -> None:
    g, rest = make_gmail()
    message = {
        "id": "m1",
        "threadId": "t1",
        "payload": {
            "mimeType": "multipart/mixed",
            "headers": [],
            "parts": [
                {"mimeType": "application/octet-stream", "body": {}},
                {"mimeType": "text/html", "body": {"data": _b64("<b>html only</b>")}},
            ],
        },
    }
    rest.get.return_value = message

    result = g.read(message_id="m1")
    assert result["body"] == "<b>html only</b>"


def test_read_raises_when_message_not_found() -> None:
    g, rest = make_gmail()
    rest.get.return_value = {}

    with pytest.raises(GoogleError, match="Message not found"):
        g.read(message_id="missing")


def test_read_calls_api_with_full_format() -> None:
    g, rest = make_gmail()
    rest.get.return_value = _message()

    g.read(message_id="abc")

    rest.get.assert_called_with(f"{_GMAIL_BASE}/messages/abc", params={"format": "full"})


def test_get_rest_builds_and_caches_lazily() -> None:
    g = ThaGmail(credentials_file="secret.json", token_file="token.json")
    mock_rest = MagicMock()
    mock_rest.post.return_value = {"id": "s1"}

    with (
        patch("tha_google_runner.gmail.build_credentials") as mock_build_creds,
        patch("tha_google_runner.gmail.RestClient") as mock_rest_cls,
    ):
        mock_build_creds.return_value = "creds"
        mock_rest_cls.return_value = mock_rest
        g.send(to="a@b.com", subject="x", body="y")
        g.send(to="a@b.com", subject="x", body="y")

    mock_build_creds.assert_called_once_with("secret.json", "token.json", g._scopes)
    mock_rest_cls.assert_called_once_with("creds", backend="requests")
