from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from tha_google_runner._rest import RestClient
from tha_google_runner.errors import GoogleHttpError


def _mock_result(code: int, data: object = None, raw_response: object = None) -> dict[str, object]:
    return {
        "status": None,
        "code": code,
        "data": data,
        "message": None,
        "raw_response": raw_response,
    }


def _make_client(creds: MagicMock | None = None) -> tuple[RestClient, MagicMock]:
    creds = creds if creds is not None else MagicMock(valid=True, token="tok")
    return RestClient(creds), creds


# ---------------------------------------------------------------------------
# _auth_header
# ---------------------------------------------------------------------------


def test_auth_header_uses_existing_valid_token() -> None:
    client, creds = _make_client(MagicMock(valid=True, token="tok"))
    header = client._auth_header()
    creds.refresh.assert_not_called()
    assert header == {"Authorization": "Bearer tok"}


def test_auth_header_refreshes_when_invalid() -> None:
    creds = MagicMock(valid=False, token="fresh")
    client, _ = _make_client(creds)
    header = client._auth_header()
    creds.refresh.assert_called_once()
    assert header == {"Authorization": "Bearer fresh"}


# ---------------------------------------------------------------------------
# get / post / patch / delete
# ---------------------------------------------------------------------------


def test_get_returns_data_on_success() -> None:
    client, _ = _make_client()
    with patch.object(client._req, "safe_call", return_value=_mock_result(200, {"a": 1})):
        assert client.get("https://example.com") == {"a": 1}


def test_get_passes_params() -> None:
    client, _ = _make_client()
    with patch.object(client._req, "safe_call", return_value=_mock_result(200, {})) as mock_call:
        client.get("https://example.com", params={"q": "x"})
    _, kwargs = mock_call.call_args
    assert kwargs["params"] == {"q": "x"}


def test_post_sends_json_body() -> None:
    client, _ = _make_client()
    with patch.object(
        client._req, "safe_call", return_value=_mock_result(200, {"ok": True})
    ) as mock_call:
        result = client.post("https://example.com", json={"x": 1})
    assert result == {"ok": True}
    _, kwargs = mock_call.call_args
    assert kwargs["json"] == {"x": 1}


def test_put_sends_json_body() -> None:
    client, _ = _make_client()
    with patch.object(
        client._req, "safe_call", return_value=_mock_result(200, {"ok": True})
    ) as mock_call:
        result = client.put("https://example.com", json={"x": 1})
    assert result == {"ok": True}
    args, kwargs = mock_call.call_args
    assert args[1] == "PUT"
    assert kwargs["json"] == {"x": 1}


def test_patch_and_delete_use_correct_methods() -> None:
    client, _ = _make_client()
    with patch.object(client._req, "safe_call", return_value=_mock_result(200, {})) as mock_call:
        client.patch("https://example.com", json={"x": 1})
        client.delete("https://example.com")
    methods = [call.args[1] for call in mock_call.call_args_list]
    assert methods == ["PATCH", "DELETE"]


def test_request_includes_auth_header() -> None:
    client, _ = _make_client(MagicMock(valid=True, token="secret-tok"))
    with patch.object(client._req, "safe_call", return_value=_mock_result(200, {})) as mock_call:
        client.get("https://example.com")
    _, kwargs = mock_call.call_args
    assert kwargs["headers"]["Authorization"] == "Bearer secret-tok"


def test_download_returns_raw_content() -> None:
    client, _ = _make_client()
    raw = MagicMock(content=b"binary-data")
    with patch.object(client._req, "safe_call", return_value=_mock_result(200, None, raw)):
        assert client.download("https://example.com") == b"binary-data"


# ---------------------------------------------------------------------------
# error + retry behavior
# ---------------------------------------------------------------------------


def test_non_2xx_raises_google_http_error() -> None:
    client, _ = _make_client()
    with patch.object(client._req, "safe_call", return_value=_mock_result(404, {"error": "nope"})):
        with pytest.raises(GoogleHttpError) as exc_info:
            client.get("https://example.com")
    assert exc_info.value.status_code == 404
    assert exc_info.value.data == {"error": "nope"}


def test_none_code_raises_google_http_error() -> None:
    client, _ = _make_client()
    with patch.object(client._req, "safe_call", return_value=_mock_result(None, None)):
        with pytest.raises(GoogleHttpError) as exc_info:
            client.get("https://example.com")
    assert exc_info.value.status_code is None


def test_retries_on_429_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("time.sleep", lambda _: None)
    client, _ = _make_client()
    responses = [_mock_result(429), _mock_result(429), _mock_result(200, {"ok": True})]
    with patch.object(client._req, "safe_call", side_effect=responses):
        assert client.get("https://example.com") == {"ok": True}


def test_does_not_retry_non_429_error() -> None:
    client, _ = _make_client()
    with patch.object(
        client._req, "safe_call", return_value=_mock_result(500, {"error": "boom"})
    ) as mock_call:
        with pytest.raises(GoogleHttpError):
            client.get("https://example.com")
    assert mock_call.call_count == 1
