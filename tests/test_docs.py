from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from tha_google_runner.docs import (
    _DOCS_BASE,
    ThaDocs,
    _extract_text,
    _get_tab_body,
    _map_char_to_index,
    _text_runs,
)
from tha_google_runner.errors import GoogleError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_body(text: str) -> dict[str, Any]:
    n = len(text)
    return {
        "content": [
            {"paragraph": {"elements": [{"startIndex": 1, "textRun": {"content": text}}]}},
            {"endIndex": n + 2},
        ]
    }


def _make_doc(text: str = "hello") -> dict[str, Any]:
    return {"body": _make_body(text)}


def _make_tabbed_doc(tab_a: str = "tab a text", tab_b: str = "tab b text") -> dict[str, Any]:
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


def make_docs(doc_response: dict[str, Any] | None = None) -> tuple[ThaDocs, MagicMock]:
    rest = MagicMock()
    if doc_response is not None:
        rest.get.return_value = doc_response
    rest.post.return_value = {"replies": [{"replaceAllText": {"occurrencesChanged": 1}}]}
    docs = ThaDocs()
    docs._rest = rest
    return docs, rest


def _batch_update_requests(rest: MagicMock) -> list[dict[str, Any]]:
    _, kwargs = rest.post.call_args
    return kwargs["json"]["requests"]  # type: ignore[no-any-return]


# ---------------------------------------------------------------------------
# _get_rest
# ---------------------------------------------------------------------------


def test_get_rest_builds_and_caches_lazily() -> None:
    docs = ThaDocs(credentials_file="secret.json", token_file="token.json")
    mock_rest = MagicMock()
    mock_rest.get.return_value = _make_doc()

    with (
        patch("tha_google_runner.docs.build_credentials") as mock_build_creds,
        patch("tha_google_runner.docs.RestClient") as mock_rest_cls,
    ):
        mock_build_creds.return_value = "creds"
        mock_rest_cls.return_value = mock_rest
        docs.read(doc_id="d1")
        docs.read(doc_id="d1")

    mock_build_creds.assert_called_once_with("secret.json", "token.json", docs._scopes)
    mock_rest_cls.assert_called_once_with("creds", backend="requests")


# ---------------------------------------------------------------------------
# _resolve_id
# ---------------------------------------------------------------------------


def test_resolve_id_accepts_raw_id() -> None:
    docs, rest = make_docs(_make_doc())
    docs.read(doc_id="abc123")
    rest.get.assert_called_with(f"{_DOCS_BASE}/abc123", params={"includeTabsContent": "true"})


def test_resolve_id_accepts_url() -> None:
    docs, rest = make_docs(_make_doc())
    docs.read(url="https://docs.google.com/document/d/abc123/edit")
    rest.get.assert_called_with(f"{_DOCS_BASE}/abc123", params={"includeTabsContent": "true"})


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
    docs, rest = make_docs(_make_doc("hello"))
    docs.append(" world", doc_id="d1")
    req = _batch_update_requests(rest)[0]
    assert req["insertText"]["text"] == " world"
    assert "tabId" not in req["insertText"]["location"]


def test_append_includes_tab_id_in_location() -> None:
    docs, rest = make_docs(_make_tabbed_doc("content here", "other"))
    docs.append(" appended", doc_id="d1", tab_id="t.aaa")
    req = _batch_update_requests(rest)[0]
    assert req["insertText"]["location"]["tabId"] == "t.aaa"
    assert req["insertText"]["text"] == " appended"


# ---------------------------------------------------------------------------
# insert_after
# ---------------------------------------------------------------------------


def test_insert_after_inserts_text() -> None:
    docs, rest = make_docs(_make_doc("hello world"))
    docs.insert_after(" there", after="hello", doc_id="d1")
    req = _batch_update_requests(rest)[0]
    assert req["insertText"]["text"] == " there"


def test_insert_after_raises_when_not_found() -> None:
    docs, _ = make_docs(_make_doc("hello world"))
    with pytest.raises(GoogleError, match="String not found"):
        docs.insert_after("x", after="missing", doc_id="d1")


def test_insert_after_at_very_end_of_text() -> None:
    docs, rest = make_docs(_make_doc("hello world"))
    docs.insert_after("!", after="world", doc_id="d1")
    req = _batch_update_requests(rest)[0]
    assert req["insertText"]["text"] == "!"
    assert req["insertText"]["location"]["index"] == 12


def test_insert_after_includes_tab_id_in_location() -> None:
    docs, rest = make_docs(_make_tabbed_doc("hello world", "other"))
    docs.insert_after(" there", after="hello", doc_id="d1", tab_id="t.aaa")
    req = _batch_update_requests(rest)[0]
    assert req["insertText"]["location"]["tabId"] == "t.aaa"


# ---------------------------------------------------------------------------
# replace
# ---------------------------------------------------------------------------


def test_replace_returns_occurrence_count() -> None:
    docs, _ = make_docs(_make_doc("hello hello"))
    count = docs.replace(old_text="hello", new_text="hi", doc_id="d1")
    assert count == 1


def test_replace_passes_match_case_false() -> None:
    docs, rest = make_docs(_make_doc())
    docs.replace(old_text="Hello", new_text="Hi", doc_id="d1", match_case=False)
    req = _batch_update_requests(rest)[0]
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


def test_map_char_to_index_past_last_run_returns_run_end() -> None:
    assert _map_char_to_index([(1, "hello")], 5) == 6


def test_map_char_to_index_empty_runs_returns_one() -> None:
    assert _map_char_to_index([], 0) == 1


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
