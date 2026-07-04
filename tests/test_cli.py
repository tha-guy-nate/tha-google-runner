from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tha_google_runner import auth, cli

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _argv(*args: str) -> list[str]:
    return ["tha-google-init", *args]


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------


def test_init_errors_when_client_secret_path_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    config_dir = tmp_path / "config"
    monkeypatch.setattr(auth, "_CONFIG_DIR", config_dir)
    monkeypatch.setattr(sys, "argv", _argv("--client-secret", str(tmp_path / "missing.json")))

    with pytest.raises(SystemExit) as exc:
        cli.init()

    assert exc.value.code == 1
    assert "file not found" in capsys.readouterr().out


def test_init_errors_when_no_client_secret_available(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    config_dir = tmp_path / "config"
    default_secret = config_dir / "client_secret.json"
    monkeypatch.setattr(auth, "_CONFIG_DIR", config_dir)
    monkeypatch.setattr(auth, "_DEFAULT_CLIENT_SECRET", default_secret)
    monkeypatch.setattr(sys, "argv", _argv())

    with pytest.raises(SystemExit) as exc:
        cli.init()

    assert exc.value.code == 1
    assert "No client_secret.json found" in capsys.readouterr().out
    assert config_dir.exists()


def test_init_copies_provided_client_secret(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_dir = tmp_path / "config"
    default_secret = config_dir / "client_secret.json"
    default_token = config_dir / "token.json"
    src = tmp_path / "downloaded.json"
    src.write_text("{}")

    monkeypatch.setattr(auth, "_CONFIG_DIR", config_dir)
    monkeypatch.setattr(auth, "_DEFAULT_CLIENT_SECRET", default_secret)
    monkeypatch.setattr(auth, "_DEFAULT_TOKEN", default_token)
    monkeypatch.setattr(sys, "argv", _argv("--client-secret", str(src)))

    mock_creds = MagicMock()
    mock_creds.to_json.return_value = "{}"

    with patch("google_auth_oauthlib.flow.InstalledAppFlow") as mock_flow_cls:
        mock_flow_cls.from_client_secrets_file.return_value.run_local_server.return_value = (
            mock_creds
        )
        cli.init()

    assert default_secret.exists()
    assert default_token.exists()


def test_init_runs_flow_when_no_token(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_dir = tmp_path / "config"
    default_secret = config_dir / "client_secret.json"
    default_token = config_dir / "token.json"
    config_dir.mkdir(parents=True)
    default_secret.write_text("{}")

    monkeypatch.setattr(auth, "_CONFIG_DIR", config_dir)
    monkeypatch.setattr(auth, "_DEFAULT_CLIENT_SECRET", default_secret)
    monkeypatch.setattr(auth, "_DEFAULT_TOKEN", default_token)
    monkeypatch.setattr(sys, "argv", _argv())

    mock_creds = MagicMock()
    mock_creds.to_json.return_value = "{}"

    with patch("google_auth_oauthlib.flow.InstalledAppFlow") as mock_flow_cls:
        mock_flow_cls.from_client_secrets_file.return_value.run_local_server.return_value = (
            mock_creds
        )
        cli.init()

    mock_flow_cls.from_client_secrets_file.assert_called_once_with(
        str(default_secret), list(auth._FULL_SCOPES)
    )
    assert default_token.exists()


def test_init_uses_custom_scopes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_dir = tmp_path / "config"
    default_secret = config_dir / "client_secret.json"
    default_token = config_dir / "token.json"
    config_dir.mkdir(parents=True)
    default_secret.write_text("{}")

    monkeypatch.setattr(auth, "_CONFIG_DIR", config_dir)
    monkeypatch.setattr(auth, "_DEFAULT_CLIENT_SECRET", default_secret)
    monkeypatch.setattr(auth, "_DEFAULT_TOKEN", default_token)
    monkeypatch.setattr(sys, "argv", _argv("--scope", "https://www.googleapis.com/auth/drive"))

    mock_creds = MagicMock()
    mock_creds.to_json.return_value = "{}"

    with patch("google_auth_oauthlib.flow.InstalledAppFlow") as mock_flow_cls:
        mock_flow_cls.from_client_secrets_file.return_value.run_local_server.return_value = (
            mock_creds
        )
        cli.init()

    mock_flow_cls.from_client_secrets_file.assert_called_once_with(
        str(default_secret), ["https://www.googleapis.com/auth/drive"]
    )


def test_init_skips_flow_when_token_valid(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_dir = tmp_path / "config"
    default_secret = config_dir / "client_secret.json"
    default_token = config_dir / "token.json"
    config_dir.mkdir(parents=True)
    default_secret.write_text("{}")
    default_token.write_text(json.dumps({"scopes": list(auth._FULL_SCOPES)}))

    monkeypatch.setattr(auth, "_CONFIG_DIR", config_dir)
    monkeypatch.setattr(auth, "_DEFAULT_CLIENT_SECRET", default_secret)
    monkeypatch.setattr(auth, "_DEFAULT_TOKEN", default_token)
    monkeypatch.setattr(sys, "argv", _argv())

    mock_creds = MagicMock()
    mock_creds.valid = True

    with (
        patch("google.oauth2.credentials.Credentials") as mock_creds_cls,
        patch("google_auth_oauthlib.flow.InstalledAppFlow") as mock_flow_cls,
    ):
        mock_creds_cls.from_authorized_user_info.return_value = mock_creds
        cli.init()

    mock_flow_cls.from_client_secrets_file.assert_not_called()


def test_init_refreshes_expired_token(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_dir = tmp_path / "config"
    default_secret = config_dir / "client_secret.json"
    default_token = config_dir / "token.json"
    config_dir.mkdir(parents=True)
    default_secret.write_text("{}")
    default_token.write_text(json.dumps({"scopes": list(auth._FULL_SCOPES)}))

    monkeypatch.setattr(auth, "_CONFIG_DIR", config_dir)
    monkeypatch.setattr(auth, "_DEFAULT_CLIENT_SECRET", default_secret)
    monkeypatch.setattr(auth, "_DEFAULT_TOKEN", default_token)
    monkeypatch.setattr(sys, "argv", _argv())

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
        cli.init()

    mock_creds.refresh.assert_called_once_with(mock_request_cls.return_value)
    mock_flow_cls.from_client_secrets_file.assert_not_called()
