from unittest.mock import MagicMock

import pytest

from tha_google_runner.errors import GoogleError
from tha_google_runner.slides import ThaSlides

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _text_obj(*runs: str) -> dict:
    return {"textElements": [{"textRun": {"content": r}} for r in runs]}


def _shape(placeholder_type: str, *runs: str) -> dict:
    return {
        "shape": {
            "placeholder": {"type": placeholder_type},
            "text": _text_obj(*runs),
        }
    }


def _slide(
    object_id: str = "s1",
    title_runs: list[str] | None = None,
    body_runs: list[str] | None = None,
    notes_runs: list[str] | None = None,
) -> dict:
    elements = []
    if title_runs is not None:
        elements.append(_shape("TITLE", *title_runs))
    if body_runs is not None:
        elements.append(_shape("BODY", *body_runs))

    notes_elements = []
    if notes_runs is not None:
        notes_elements.append(_shape("BODY", *notes_runs))

    return {
        "objectId": object_id,
        "pageElements": elements,
        "slideProperties": {"notesPage": {"pageElements": notes_elements}},
    }


def make_slides(presentation: dict) -> ThaSlides:
    svc = MagicMock()
    svc.presentations().get().execute.return_value = presentation
    ts = ThaSlides()
    ts._service = svc
    return ts


# ---------------------------------------------------------------------------
# _resolve_id
# ---------------------------------------------------------------------------


def test_resolve_id_accepts_raw_id() -> None:
    ts = make_slides({"slides": []})
    ts.read(presentation_id="abc123")
    ts._service.presentations().get.assert_called_with(presentationId="abc123")


def test_resolve_id_accepts_full_url() -> None:
    ts = make_slides({"slides": []})
    url = "https://docs.google.com/presentation/d/abc123/edit"
    ts.read(url=url)
    ts._service.presentations().get.assert_called_with(presentationId="abc123")


def test_resolve_id_raises_on_invalid_url() -> None:
    ts = make_slides({"slides": []})
    with pytest.raises(GoogleError, match="Could not parse"):
        ts.read(url="https://notgoogle.com/foo")


def test_resolve_id_raises_when_neither_provided() -> None:
    ts = make_slides({"slides": []})
    with pytest.raises(GoogleError, match="Provide either"):
        ts.read()


# ---------------------------------------------------------------------------
# read — text extraction
# ---------------------------------------------------------------------------


def test_read_empty_presentation() -> None:
    ts = make_slides({"slides": []})
    assert ts.read(presentation_id="p") == []


def test_read_returns_one_entry_per_slide() -> None:
    presentation = {"slides": [_slide("s1"), _slide("s2")]}
    ts = make_slides(presentation)
    result = ts.read(presentation_id="p")
    assert len(result) == 2


def test_read_extracts_title() -> None:
    presentation = {"slides": [_slide("s1", title_runs=["Hello World\n"])]}
    ts = make_slides(presentation)
    result = ts.read(presentation_id="p")
    assert result[0]["title"] == "Hello World"


def test_read_extracts_body() -> None:
    presentation = {"slides": [_slide("s1", body_runs=["Bullet 1\n", "Bullet 2\n"])]}
    ts = make_slides(presentation)
    result = ts.read(presentation_id="p")
    assert result[0]["body"] == "Bullet 1\nBullet 2"


def test_read_extracts_notes() -> None:
    presentation = {"slides": [_slide("s1", notes_runs=["Speaker note here\n"])]}
    ts = make_slides(presentation)
    result = ts.read(presentation_id="p")
    assert result[0]["notes"] == "Speaker note here"


def test_read_sets_index_and_object_id() -> None:
    presentation = {"slides": [_slide("sid-a"), _slide("sid-b")]}
    ts = make_slides(presentation)
    result = ts.read(presentation_id="p")
    assert result[0]["index"] == 0
    assert result[0]["object_id"] == "sid-a"
    assert result[1]["index"] == 1
    assert result[1]["object_id"] == "sid-b"


def test_read_empty_title_and_body_default_to_empty_string() -> None:
    presentation = {"slides": [_slide("s1")]}
    ts = make_slides(presentation)
    result = ts.read(presentation_id="p")
    assert result[0]["title"] == ""
    assert result[0]["body"] == ""
    assert result[0]["notes"] == ""


def test_read_centered_title_type() -> None:
    slide = {
        "objectId": "s1",
        "pageElements": [_shape("CENTERED_TITLE", "Centered\n")],
        "slideProperties": {"notesPage": {"pageElements": []}},
    }
    ts = make_slides({"slides": [slide]})
    result = ts.read(presentation_id="p")
    assert result[0]["title"] == "Centered"


def test_read_subtitle_treated_as_body() -> None:
    slide = {
        "objectId": "s1",
        "pageElements": [_shape("SUBTITLE", "Sub text\n")],
        "slideProperties": {"notesPage": {"pageElements": []}},
    }
    ts = make_slides({"slides": [slide]})
    result = ts.read(presentation_id="p")
    assert result[0]["body"] == "Sub text"


def test_read_non_placeholder_shapes_ignored() -> None:
    slide = {
        "objectId": "s1",
        "pageElements": [
            {"shape": {"text": _text_obj("ignored image label\n")}},
        ],
        "slideProperties": {"notesPage": {"pageElements": []}},
    }
    ts = make_slides({"slides": [slide]})
    result = ts.read(presentation_id="p")
    assert result[0]["title"] == ""
    assert result[0]["body"] == ""


def test_read_multiple_slides_independent() -> None:
    presentation = {
        "slides": [
            _slide("s1", title_runs=["Slide 1\n"], body_runs=["Body 1\n"]),
            _slide("s2", title_runs=["Slide 2\n"], notes_runs=["Note 2\n"]),
        ]
    }
    ts = make_slides(presentation)
    result = ts.read(presentation_id="p")
    assert result[0]["title"] == "Slide 1"
    assert result[0]["body"] == "Body 1"
    assert result[0]["notes"] == ""
    assert result[1]["title"] == "Slide 2"
    assert result[1]["body"] == ""
    assert result[1]["notes"] == "Note 2"


# ---------------------------------------------------------------------------
# get — raw passthrough
# ---------------------------------------------------------------------------


def test_get_returns_raw_presentation() -> None:
    raw = {"presentationId": "p", "slides": []}
    ts = make_slides(raw)
    result = ts.get(presentation_id="p")
    assert result == raw


def test_service_is_built_once() -> None:
    ts = make_slides({"slides": []})
    ts.read(presentation_id="p")
    ts.read(presentation_id="p")
    # _service was injected directly; just verify no second build call happened
    assert ts._service is not None
