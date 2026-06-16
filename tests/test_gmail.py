import base64
from email import message_from_bytes
from unittest.mock import MagicMock

from tha_google_runner.gmail import ThaGmail

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_gmail() -> tuple[ThaGmail, MagicMock]:
    svc = MagicMock()
    g = ThaGmail()
    g._service = svc
    return g, svc


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
) -> dict:
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
    g, svc = make_gmail()
    svc.users().messages().send().execute.return_value = {"id": "sent1"}

    result = g.send(to="a@example.com", subject="Hi", body="Hello")

    assert result == {"id": "sent1"}
    call_kwargs = svc.users().messages().send.call_args[1]
    assert call_kwargs["userId"] == "me"
    raw = base64.urlsafe_b64decode(call_kwargs["body"]["raw"] + "==")
    parsed = message_from_bytes(raw)
    assert parsed["to"] == "a@example.com"
    assert parsed["subject"] == "Hi"


def test_send_list_of_recipients() -> None:
    g, svc = make_gmail()
    svc.users().messages().send().execute.return_value = {"id": "sent1"}

    g.send(to=["a@example.com", "b@example.com"], subject="Hi", body="Hello")

    call_kwargs = svc.users().messages().send.call_args[1]
    raw = base64.urlsafe_b64decode(call_kwargs["body"]["raw"] + "==")
    parsed = message_from_bytes(raw)
    assert "a@example.com" in parsed["to"]
    assert "b@example.com" in parsed["to"]


def test_send_with_cc_and_bcc() -> None:
    g, svc = make_gmail()
    svc.users().messages().send().execute.return_value = {"id": "s1"}

    g.send(to="a@example.com", subject="Hi", body="Hello", cc="c@example.com", bcc="b@example.com")

    call_kwargs = svc.users().messages().send.call_args[1]
    raw = base64.urlsafe_b64decode(call_kwargs["body"]["raw"] + "==")
    parsed = message_from_bytes(raw)
    assert parsed["cc"] == "c@example.com"
    assert parsed["bcc"] == "b@example.com"


def test_send_html_uses_multipart() -> None:
    g, svc = make_gmail()
    svc.users().messages().send().execute.return_value = {"id": "s1"}

    g.send(to="a@example.com", subject="Hi", body="<b>Hello</b>", html=True)

    call_kwargs = svc.users().messages().send.call_args[1]
    raw = base64.urlsafe_b64decode(call_kwargs["body"]["raw"] + "==")
    parsed = message_from_bytes(raw)
    assert parsed.get_content_type() == "multipart/alternative"


# ---------------------------------------------------------------------------
# list_messages
# ---------------------------------------------------------------------------


def test_list_messages_returns_messages() -> None:
    g, svc = make_gmail()
    msgs = [{"id": "1", "threadId": "t1"}, {"id": "2", "threadId": "t2"}]
    svc.users().messages().list().execute.return_value = {"messages": msgs, "nextPageToken": None}

    result = g.list_messages()
    assert result == msgs


def test_list_messages_passes_query() -> None:
    g, svc = make_gmail()
    svc.users().messages().list().execute.return_value = {"messages": [], "nextPageToken": None}

    g.list_messages(query="from:boss@example.com")

    call_kwargs = svc.users().messages().list.call_args[1]
    assert call_kwargs["q"] == "from:boss@example.com"


def test_list_messages_paginates() -> None:
    g, svc = make_gmail()
    svc.users().messages().list().execute.side_effect = [
        {"messages": [{"id": "1"}], "nextPageToken": "tok"},
        {"messages": [{"id": "2"}], "nextPageToken": None},
    ]

    result = g.list_messages()
    assert [m["id"] for m in result] == ["1", "2"]


def test_list_messages_respects_max_results() -> None:
    g, svc = make_gmail()
    msgs = [{"id": str(i)} for i in range(10)]
    svc.users().messages().list().execute.return_value = {"messages": msgs, "nextPageToken": None}

    result = g.list_messages(max_results=3)
    assert len(result) == 3


# ---------------------------------------------------------------------------
# read
# ---------------------------------------------------------------------------


def test_read_returns_parsed_message() -> None:
    g, svc = make_gmail()
    svc.users().messages().get().execute.return_value = _message(
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
    g, svc = make_gmail()
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
    svc.users().messages().get().execute.return_value = message

    result = g.read(message_id="m1")
    assert result["body"] == "plain text"


def test_read_calls_api_with_full_format() -> None:
    g, svc = make_gmail()
    svc.users().messages().get().execute.return_value = _message()

    g.read(message_id="abc")

    svc.users().messages().get.assert_called_with(userId="me", id="abc", format="full")


def test_service_is_built_once() -> None:
    g, _ = make_gmail()
    svc = MagicMock()
    svc.users().messages().send().execute.return_value = {"id": "s1"}
    g._service = svc

    g.send(to="a@b.com", subject="x", body="y")
    g.send(to="a@b.com", subject="x", body="y")

    assert g._service is svc
