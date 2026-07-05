from __future__ import annotations

import random
import time
from collections.abc import Callable
from typing import Any, TypeVar

T = TypeVar("T")


class GoogleError(Exception):
    """Raised for tha-google-runner errors."""


class GoogleHttpError(GoogleError):
    """Raised by RestClient for non-2xx responses from a Google REST API.

    Mirrors googleapiclient's HttpError shape (`exc.resp.status`) closely enough
    that existing `except ...: if status == 404` call sites port over with a
    one-line change to `exc.status_code`.
    """

    def __init__(self, status_code: int | None, data: Any, message: str | None) -> None:
        self.status_code = status_code
        self.data = data
        super().__init__(message or f"Google API error (status {status_code})")


def retry_rate_limited(fn: Callable[[], T], *, max_attempts: int = 5, base_delay: float = 1.0) -> T:
    """Retry fn only on a 429 GoogleHttpError.

    A 429 means Google rejected the request before processing it, so retrying
    is safe regardless of HTTP method — unlike a 5xx on a non-idempotent
    POST/PATCH, where a retry risks double-applying a partially-completed
    write. That case is left to RestClient's transport-level adapter retry,
    which only covers safe (idempotent) methods.
    """
    for attempt in range(max_attempts):
        try:
            return fn()
        except GoogleHttpError as exc:
            if exc.status_code != 429 or attempt == max_attempts - 1:
                raise
            time.sleep(base_delay * (2**attempt) + random.uniform(0, 1))
    raise AssertionError("unreachable")  # pragma: no cover


def _is_rate_limited(exc: BaseException) -> bool:
    try:
        import gspread.exceptions

        if isinstance(exc, gspread.exceptions.APIError) and exc.response.status_code == 429:
            return True
    except Exception:  # pragma: no cover — gspread is a required dep, always importable
        pass
    try:
        from googleapiclient.errors import HttpError

        if isinstance(exc, HttpError) and exc.resp.status == 429:
            return True
    except Exception:  # pragma: no cover — google-api-python-client is a required dep
        pass
    return False


def with_retry(fn: Callable[[], T], *, max_attempts: int = 5, base_delay: float = 1.0) -> T:
    for attempt in range(max_attempts):
        try:
            return fn()
        except Exception as exc:
            if not _is_rate_limited(exc) or attempt == max_attempts - 1:
                raise
            time.sleep(base_delay * (2**attempt) + random.uniform(0, 1))
    raise AssertionError("unreachable")  # pragma: no cover
