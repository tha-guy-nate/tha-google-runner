from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import google.auth.exceptions
import pytest

from tha_google_runner import auth
from tha_google_runner.errors import GoogleError

# ---------------------------------------------------------------------------
# build_credentials
# ---------------------------------------------------------------------------


def test_build_credentials_uses_explicit_file() -> None:
    with patch.object(auth, "_oauth_credentials") as mock_oauth:
        mock_oauth.return_value = "creds"
        result = auth.build_credentials("explicit.json", "token.json", ["scope-a"])

    mock_oauth.assert_called_once_with("explicit.json", "token.json", ["scope-a"])
    assert result == "creds"


def test_build_credentials_uses_default_client_secret_file(tmp_path: Path) -> None:
    default_secret = tmp_path / "client_secret.json"
    default_secret.write_text("{}")

    with (
        patch.object(auth, "_DEFAULT_CLIENT_SECRET", default_secret),
        patch.object(auth, "_oauth_credentials") as mock_oauth,
    ):
        mock_oauth.return_value = "creds"
        result = auth.build_credentials(None, None)

    mock_oauth.assert_called_once_with(str(default_secret), None, auth._DEFAULT_SCOPES)
    assert result == "creds"


def test_build_credentials_falls_back_to_adc(tmp_path: Path) -> None:
    missing_secret = tmp_path / "client_secret.json"

    with (
        patch.object(auth, "_DEFAULT_CLIENT_SECRET", missing_secret),
        patch.object(auth.google.auth, "default") as mock_default,
    ):
        mock_default.return_value = ("adc-creds", "project-id")
        result = auth.build_credentials(None, None)

    mock_default.assert_called_once_with(scopes=auth._DEFAULT_SCOPES)
    assert result == "adc-creds"


def test_build_credentials_raises_when_no_creds(tmp_path: Path) -> None:
    missing_secret = tmp_path / "client_secret.json"

    with (
        patch.object(auth, "_DEFAULT_CLIENT_SECRET", missing_secret),
        patch.object(auth.google.auth, "default") as mock_default,
    ):
        mock_default.side_effect = google.auth.exceptions.DefaultCredentialsError("no creds")
        with pytest.raises(GoogleError, match="No Google credentials found"):
            auth.build_credentials(None, None)


# ---------------------------------------------------------------------------
# _oauth_credentials
# ---------------------------------------------------------------------------


def test_oauth_credentials_runs_flow_when_no_token(tmp_path: Path) -> None:
    token_path = tmp_path / "token.json"
    mock_creds = MagicMock()
    mock_creds.to_json.return_value = "{}"

    with patch("google_auth_oauthlib.flow.InstalledAppFlow") as mock_flow_cls:
        mock_flow_cls.from_client_secrets_file.return_value.run_local_server.return_value = (
            mock_creds
        )
        result = auth._oauth_credentials("secret.json", str(token_path), ["scope-a"])

    mock_flow_cls.from_client_secrets_file.assert_called_once_with("secret.json", ["scope-a"])
    assert result is mock_creds
    assert token_path.exists()


def test_oauth_credentials_returns_valid_cached_token(tmp_path: Path) -> None:
    token_path = tmp_path / "token.json"
    token_path.write_text(json.dumps({"scopes": ["scope-a"]}))

    mock_creds = MagicMock()
    mock_creds.valid = True

    with (
        patch("google.oauth2.credentials.Credentials") as mock_creds_cls,
        patch("google_auth_oauthlib.flow.InstalledAppFlow") as mock_flow_cls,
    ):
        mock_creds_cls.from_authorized_user_info.return_value = mock_creds
        result = auth._oauth_credentials("secret.json", str(token_path), ["scope-a"])

    mock_flow_cls.from_client_secrets_file.assert_not_called()
    assert result is mock_creds


def test_oauth_credentials_refreshes_expired_token(tmp_path: Path) -> None:
    token_path = tmp_path / "token.json"
    token_path.write_text(json.dumps({"scopes": ["scope-a"]}))

    mock_creds = MagicMock()
    mock_creds.valid = False
    mock_creds.expired = True
    mock_creds.refresh_token = "refresh-token"
    mock_creds.to_json.return_value = "{}"

    with (
        patch("google.oauth2.credentials.Credentials") as mock_creds_cls,
        patch("google.auth.transport.requests.Request") as mock_request_cls,
        patch("google_auth_oauthlib.flow.InstalledAppFlow") as mock_flow_cls,
    ):
        mock_creds_cls.from_authorized_user_info.return_value = mock_creds
        result = auth._oauth_credentials("secret.json", str(token_path), ["scope-a"])

    mock_creds.refresh.assert_called_once_with(mock_request_cls.return_value)
    mock_flow_cls.from_client_secrets_file.assert_not_called()
    assert result is mock_creds


def test_oauth_credentials_expands_scopes_when_token_missing_requested_scope(
    tmp_path: Path,
) -> None:
    token_path = tmp_path / "token.json"
    token_path.write_text(json.dumps({"scopes": ["scope-old"]}))

    mock_creds = MagicMock()
    mock_creds.valid = True

    with patch("google.oauth2.credentials.Credentials") as mock_creds_cls:
        mock_creds_cls.from_authorized_user_info.return_value = mock_creds
        auth._oauth_credentials("secret.json", str(token_path), ["scope-new"])

    _called_data, called_scopes = mock_creds_cls.from_authorized_user_info.call_args[0]
    assert set(called_scopes) == {"scope-old", "scope-new"}
