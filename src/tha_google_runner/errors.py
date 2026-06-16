from __future__ import annotations

import random
import time
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")


class GoogleError(Exception):
    """Raised for tha-google-runner errors."""


def _is_rate_limited(exc: BaseException) -> bool:
    try:
        import gspread.exceptions

        if isinstance(exc, gspread.exceptions.APIError) and exc.response.status_code == 429:
            return True
    except Exception:
        pass
    try:
        from googleapiclient.errors import HttpError

        if isinstance(exc, HttpError) and exc.resp.status == 429:
            return True
    except Exception:
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
    raise AssertionError("unreachable")
