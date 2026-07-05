from __future__ import annotations

import pytest

from tha_google_runner.errors import GoogleError, GoogleHttpError, retry_rate_limited

# ---------------------------------------------------------------------------
# GoogleError
# ---------------------------------------------------------------------------


def test_google_error_is_exception() -> None:
    with pytest.raises(GoogleError, match="boom"):
        raise GoogleError("boom")


# ---------------------------------------------------------------------------
# GoogleHttpError
# ---------------------------------------------------------------------------


def test_google_http_error_carries_status_and_data() -> None:
    exc = GoogleHttpError(404, {"error": "not found"}, None)
    assert exc.status_code == 404
    assert exc.data == {"error": "not found"}
    assert "404" in str(exc)


def test_google_http_error_uses_given_message() -> None:
    exc = GoogleHttpError(500, None, "server exploded")
    assert str(exc) == "server exploded"


def test_google_http_error_is_google_error() -> None:
    assert isinstance(GoogleHttpError(400, None, None), GoogleError)


# ---------------------------------------------------------------------------
# retry_rate_limited
# ---------------------------------------------------------------------------


def test_retry_rate_limited_returns_on_success() -> None:
    assert retry_rate_limited(lambda: 42) == 42


def test_retry_rate_limited_retries_429_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("time.sleep", lambda _: None)
    attempts = {"count": 0}

    def flaky() -> str:
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise GoogleHttpError(429, None, None)
        return "ok"

    assert retry_rate_limited(flaky, max_attempts=5, base_delay=0) == "ok"
    assert attempts["count"] == 3


def test_retry_rate_limited_raises_immediately_for_non_429() -> None:
    def always_fails() -> None:
        raise GoogleHttpError(500, None, "boom")

    with pytest.raises(GoogleHttpError):
        retry_rate_limited(always_fails, max_attempts=5)


def test_retry_rate_limited_raises_after_exhausting_attempts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("time.sleep", lambda _: None)

    def always_rate_limited() -> None:
        raise GoogleHttpError(429, None, None)

    with pytest.raises(GoogleHttpError):
        retry_rate_limited(always_rate_limited, max_attempts=2, base_delay=0)
