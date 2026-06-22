from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from tha_google_runner.docs import ThaDocs, _extract_text, _get_tab_body, _text_runs
from tha_google_runner.errors import GoogleError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_body(text: str) -> dict:
    n = len(text)
    return {
        "content": [
            {"paragraph": {"elements": [{"startIndex": 1, "textRun": {"content": text}}]}},
            {"endIndex": n + 2},
        ]
    }


def _make_doc(text: str = "hello") -> dict:
    return {"body": _make_body(text)}


def _make_tabbed_doc(tab_a: str = "tab a text", tab_b: str = "tab b text") -> dict:
    return {
        "tabs": [
            {
                "tabProperties": {"tabId": "t.aaa", "title": "First", "index": 0},
                "documentTab": {"body": _make_body(tab_a)},
            },
            {
                "tabProperties": {"tabId": "t.bbb", "title": "Second", "index": 1},
                "documentTab": {"body": _make_body(tab_b)},
            },
        ]
    }


def make_docs(doc_response: dict | None = None) -> tuple[ThaDocs, MagicMock]:
    svc = MagicMock()
    if doc_response is not None:
        svc.documents().get().execute.return_value = doc_response
    svc.documents().batchUpdate().execute.return_value = {
        "replies": [{"replaceAllText": {"occurrencesChanged": 1}}]
    }
    docs = ThaDocs()
    docs._service = svc
    return docs, svc


# ---------------------------------------------------------------------------
# _resolve_id
# ---------------------------------------------------------------------------


def test_resolve_id_accepts_raw_id() -> None:
    docs, svc = make_docs(_make_doc())
    docs.read(doc_id="abc123")
    svc.documents().get.assert_called_with(documentId="abc123", includeTabsContent=True)


def test_resolve_id_accepts_url() -> None:
    docs, svc = make_docs(_make_doc())
    docs.read(url="https://docs.google.com/document/d/abc123/edit")
    svc.documents().get.assert_called_with(documentId="abc123", includeTabsContent=True)


def test_resolve_id_raises_on_bad_url() -> None:
    docs, _ = make_docs()
    with pytest.raises(GoogleError, match="Could not parse"):
        docs.read(url="https://notgoogle.com/doc")


def test_resolve_id_raises_when_neither_provided() -> None:
    docs, _ = make_docs()
    with pytest.raises(GoogleError, match="Provide either"):
        docs.read()


# ---------------------------------------------------------------------------
# read
# ---------------------------------------------------------------------------


def test_read_returns_text_no_tabs() -> None:
    docs, _ = make_docs(_make_doc("hello world"))
    result = docs.read(doc_id="d1")
    assert result == "hello world"
    assert docs.content == "hello world"


def test_read_defaults_to_first_tab() -> None:
    docs, _ = make_docs(_make_tabbed_doc("first tab text", "second tab text"))
    result = docs.read(doc_id="d1")
    assert result == "first tab text"


def test_read_tab_by_id() -> None:
    docs, _ = make_docs(_make_tabbed_doc("first tab text", "second tab text"))
    result = docs.read(doc_id="d1", tab_id="t.bbb")
    assert result == "second tab text"


def test_read_tab_by_title() -> None:
    docs, _ = make_docs(_make_tabbed_doc("first tab text", "second tab text"))
    result = docs.read(doc_id="d1", tab_id="Second")
    assert result == "second tab text"


# ---------------------------------------------------------------------------
# append
# ---------------------------------------------------------------------------


def test_append_inserts_at_end_no_tab() -> None:
    docs, svc = make_docs(_make_doc("hello"))
    docs.append(" world", doc_id="d1")
    req = svc.documents().batchUpdate.call_args[1]["body"]["requests"][0]
    assert req["insertText"]["text"] == " world"
    assert "tabId" not in req["insertText"]["location"]


def test_append_includes_tab_id_in_location() -> None:
    docs, svc = make_docs(_make_tabbed_doc("content here", "other"))
    docs.append(" appended", doc_id="d1", tab_id="t.aaa")
    req = svc.documents().batchUpdate.call_args[1]["body"]["requests"][0]
    assert req["insertText"]["location"]["tabId"] == "t.aaa"
    assert req["insertText"]["text"] == " appended"


# ---------------------------------------------------------------------------
# insert_after
# ---------------------------------------------------------------------------


def test_insert_after_inserts_text() -> None:
    docs, svc = make_docs(_make_doc("hello world"))
    docs.insert_after(" there", after="hello", doc_id="d1")
    req = svc.documents().batchUpdate.call_args[1]["body"]["requests"][0]
    assert req["insertText"]["text"] == " there"


def test_insert_after_raises_when_not_found() -> None:
    docs, _ = make_docs(_make_doc("hello world"))
    with pytest.raises(GoogleError, match="String not found"):
        docs.insert_after("x", after="missing", doc_id="d1")


def test_insert_after_includes_tab_id_in_location() -> None:
    docs, svc = make_docs(_make_tabbed_doc("hello world", "other"))
    docs.insert_after(" there", after="hello", doc_id="d1", tab_id="t.aaa")
    req = svc.documents().batchUpdate.call_args[1]["body"]["requests"][0]
    assert req["insertText"]["location"]["tabId"] == "t.aaa"


# ---------------------------------------------------------------------------
# replace
# ---------------------------------------------------------------------------


def test_replace_returns_occurrence_count() -> None:
    docs, _ = make_docs(_make_doc("hello hello"))
    count = docs.replace(old_text="hello", new_text="hi", doc_id="d1")
    assert count == 1


def test_replace_passes_match_case_false() -> None:
    docs, svc = make_docs(_make_doc())
    docs.replace(old_text="Hello", new_text="Hi", doc_id="d1", match_case=False)
    req = svc.documents().batchUpdate.call_args[1]["body"]["requests"][0]
    assert req["replaceAllText"]["containsText"]["matchCase"] is False


# ---------------------------------------------------------------------------
# _get_tab_body
# ---------------------------------------------------------------------------


def test_get_tab_body_no_tabs_returns_doc_body() -> None:
    doc = _make_doc("plain doc")
    body = _get_tab_body(doc, None)
    assert body == doc["body"]


def test_get_tab_body_none_returns_first_tab() -> None:
    doc = _make_tabbed_doc("first", "second")
    body = _get_tab_body(doc, None)
    assert _extract_text(body) == "first"


def test_get_tab_body_by_tab_id() -> None:
    doc = _make_tabbed_doc("first", "second")
    body = _get_tab_body(doc, "t.bbb")
    assert _extract_text(body) == "second"


def test_get_tab_body_by_title() -> None:
    doc = _make_tabbed_doc("first", "second")
    body = _get_tab_body(doc, "Second")
    assert _extract_text(body) == "second"


def test_get_tab_body_raises_on_unknown_tab() -> None:
    doc = _make_tabbed_doc()
    with pytest.raises(GoogleError, match="Tab not found"):
        _get_tab_body(doc, "NonExistent")


# ---------------------------------------------------------------------------
# _text_runs / _extract_text
# ---------------------------------------------------------------------------


def test_text_runs_skips_non_paragraph_elements() -> None:
    body = {
        "content": [
            {"sectionBreak": {}},
            {"paragraph": {"elements": [{"startIndex": 1, "textRun": {"content": "hello"}}]}},
        ]
    }
    runs = _text_runs(body)
    assert runs == [(1, "hello")]


def test_extract_text_concatenates_runs() -> None:
    body = {
        "content": [
            {
                "paragraph": {
                    "elements": [
                        {"startIndex": 1, "textRun": {"content": "foo"}},
                        {"startIndex": 4, "textRun": {"content": "bar"}},
                    ]
                }
            }
        ]
    }
    assert _extract_text(body) == "foobar"
