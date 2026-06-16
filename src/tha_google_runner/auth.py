from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

import google.auth
import google.auth.exceptions
from platformdirs import user_config_dir

from tha_google_runner.errors import GoogleError

if TYPE_CHECKING:
    import google.auth.credentials

_CONFIG_DIR = Path(user_config_dir("tha-google-runner"))
_DEFAULT_TOKEN = _CONFIG_DIR / "token.json"
_DEFAULT_CLIENT_SECRET = _CONFIG_DIR / "client_secret.json"

_SCOPES = [
    "https://mail.google.com/",
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/spreadsheets",
]


def build_credentials(
    credentials_file: str | None,
    token_file: str | None,
) -> google.auth.credentials.Credentials:
    """Return Google credentials.

    Priority:
    1. credentials_file arg — explicit path to client_secrets.json
    2. Standard location — <user config dir>/tha-google-runner/client_secret.json
    3. ADC — fallback; cannot access private Docs/Drive (gcloud blocks those scopes)
    """
    resolved_file: str | None = credentials_file
    if resolved_file is None and _DEFAULT_CLIENT_SECRET.exists():
        resolved_file = str(_DEFAULT_CLIENT_SECRET)

    if resolved_file is not None:
        return _oauth_credentials(resolved_file, token_file)

    try:
        adc_creds, _ = google.auth.default(scopes=_SCOPES)
        return adc_creds
    except google.auth.exceptions.DefaultCredentialsError:
        raise GoogleError(
            "No Google credentials found. Set up credentials in one of these ways:\n"
            f"  1. Run: tha-google-init --client-secret <path/to/downloaded.json>\n"
            f"     (places your client_secret.json at {_DEFAULT_CLIENT_SECRET})\n"
            "  2. Pass credentials_file= pointing to your client_secrets.json\n"
            "  3. Run: gcloud auth application-default login\n"
            "     (ADC only — cannot access private Docs/Drive; see README)\n"
            "See the tha-google-runner README for setup instructions."
        ) from None


def _oauth_credentials(
    credentials_file: str,
    token_file: str | None,
) -> google.auth.credentials.Credentials:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    token = Path(token_file or str(_DEFAULT_TOKEN))
    token.parent.mkdir(parents=True, exist_ok=True)

    creds: Credentials | None = None
    if token.exists():
        creds = Credentials.from_authorized_user_info(json.loads(token.read_text()), _SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(credentials_file, _SCOPES)
            creds = flow.run_local_server(port=0)
        token.write_text(creds.to_json())

    return creds
