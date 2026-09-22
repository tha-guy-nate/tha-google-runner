from __future__ import annotations

from typing import Any, Literal

from google.auth.transport.requests import Request
from tha_req_runner import ThaReq

from tha_google_runner.errors import GoogleHttpError, retry_rate_limited

# 429 is retried at the app level (errors.retry_rate_limited) since it's safe
# on any HTTP method. 5xx retries are left to the transport adapter below,
# which only covers safe (idempotent) methods by default — retrying a 5xx on
# a non-idempotent POST/PATCH risks double-applying a partially-completed write.
_STATUS_FORCELIST = (500, 502, 503, 504)


class RestClient:
    """Thin REST wrapper replacing googleapiclient's discovery-based Resource objects.

    One instance per Tha* class instance (mirrors the old `self._service` /
    `self._drive_service` lazy-build pattern), holding the credentials for that
    class's scopes plus its own ThaReq transport.
    """

    def __init__(
        self, credentials: Any, *, backend: Literal["requests", "httpx2"] = "requests"
    ) -> None:
        self._creds = credentials
        self._req = ThaReq(backend=backend)

    def _auth_header(self) -> dict[str, str]:
        # Sessions are cached per-thread by ThaReq, but OAuth tokens expire
        # (~1hr) — refresh and rebuild the header on every call rather than
        # relying on session-level headers set once.
        if not self._creds.valid:
            self._creds.refresh(Request())
        return {"Authorization": f"Bearer {self._creds.token}"}

    def _call(self, method: str, url: str, **kwargs: Any) -> dict[str, Any]:
        headers = {**self._auth_header(), **(kwargs.pop("headers", None) or {})}
        session = self._req.get_session(status_forcelist=_STATUS_FORCELIST)

        def _do() -> dict[str, Any]:
            result = self._req.safe_call(session.request, method, url, headers=headers, **kwargs)
            code = result["code"]
            if code is not None and 200 <= code < 300:
                return result
            raise GoogleHttpError(code, result["data"], result["message"])

        return retry_rate_limited(_do)

    def get(self, url: str, *, params: dict[str, Any] | None = None) -> Any:
        return self._call("GET", url, params=params)["data"]

    def post(self, url: str, *, params: dict[str, Any] | None = None, json: Any = None) -> Any:
        return self._call("POST", url, params=params, json=json)["data"]

    def put(self, url: str, *, params: dict[str, Any] | None = None, json: Any = None) -> Any:
        return self._call("PUT", url, params=params, json=json)["data"]

    def patch(self, url: str, *, params: dict[str, Any] | None = None, json: Any = None) -> Any:
        return self._call("PATCH", url, params=params, json=json)["data"]

    def delete(self, url: str, *, params: dict[str, Any] | None = None) -> Any:
        return self._call("DELETE", url, params=params)["data"]

    def download(self, url: str, *, params: dict[str, Any] | None = None) -> bytes:
        """GET a binary body (Drive file content, Gmail attachments) as raw bytes."""
        result = self._call("GET", url, params=params)
        return result["raw_response"].content  # type: ignore[no-any-return]
