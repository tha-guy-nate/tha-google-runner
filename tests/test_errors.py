from __future__ import annotations

from unittest.mock import MagicMock

import gspread.exceptions
import pytest
from googleapiclient.errors import HttpError

from tha_google_runner.errors import GoogleError, _is_rate_limited, with_retry

# ---------------------------------------------------------------------------
# GoogleError
# ---------------------------------------------------------------------------


def test_google_error_is_exception() -> None:
    with pytest.raises(GoogleError, match="boom"):
        raise GoogleError("boom")


# ---------------------------------------------------------------------------
# _is_rate_limited
# ---------------------------------------------------------------------------


def make_gspread_api_error(status: int) -> gspread.exceptions.APIError:
    response = MagicMock()
    response.status_code = status
    return gspread.exceptions.APIError(response)


def make_http_error(status: int) -> HttpError:
    resp = MagicMock()
    resp.status = status
    return HttpError(resp=resp, content=b"Error")


def test_is_rate_limited_true_for_gspread_429() -> None:
    assert _is_rate_limited(make_gspread_api_error(429)) is True


def test_is_rate_limited_false_for_gspread_non_429() -> None:
    assert _is_rate_limited(make_gspread_api_error(404)) is False


def test_is_rate_limited_true_for_http_error_429() -> None:
    assert _is_rate_limited(make_http_error(429)) is True


def test_is_rate_limited_false_for_http_error_non_429() -> None:
    assert _is_rate_limited(make_http_error(500)) is False


def test_is_rate_limited_false_for_unrelated_exception() -> None:
    assert _is_rate_limited(ValueError("nope")) is False


# ---------------------------------------------------------------------------
# with_retry
# ---------------------------------------------------------------------------


def test_with_retry_returns_on_success() -> None:
    assert with_retry(lambda: 42) == 42


def test_with_retry_retries_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("time.sleep", lambda _: None)
    attempts = {"count": 0}

    def flaky() -> str:
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise make_http_error(429)
        return "ok"

    assert with_retry(flaky, max_attempts=5, base_delay=0) == "ok"
    assert attempts["count"] == 3


def test_with_retry_raises_immediately_when_not_rate_limited() -> None:
    def always_fails() -> None:
        raise ValueError("not rate limited")

    with pytest.raises(ValueError, match="not rate limited"):
        with_retry(always_fails, max_attempts=5)


def test_with_retry_raises_after_exhausting_attempts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("time.sleep", lambda _: None)

    def always_rate_limited() -> None:
        raise make_http_error(429)

    with pytest.raises(HttpError):
        with_retry(always_rate_limited, max_attempts=2, base_delay=0)
