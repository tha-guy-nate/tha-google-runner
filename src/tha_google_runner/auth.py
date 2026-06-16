from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

import google.auth
import google.auth.exceptions

from tha_google_runner.errors import GoogleError

if TYPE_CHECKING:
    import google.auth.credentials

_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/documents",
]

_DEFAULT_TOKEN = Path.home() / ".config" / "tha-google-runner" / "token.json"


def build_credentials(
    credentials_file: str | None,
    token_file: str | None,
) -> google.auth.credentials.Credentials:
    """Return raw Google credentials using ADC or an OAuth2 client_secrets.json file.

    Auth priority:
    1. Application Default Credentials (ADC) — if credentials_file is None.
       Run `gcloud auth application-default login` once to set this up.
    2. OAuth2 user flow — if credentials_file points to a client_secrets.json.
       A browser window opens on first run; the token is cached for subsequent runs.
    """
    if credentials_file is None:
        try:
            creds, _ = google.auth.default(scopes=_SCOPES)
            return creds
        except google.auth.exceptions.DefaultCredentialsError:
            raise GoogleError(
                "No Google credentials found. Either:\n"
                "  1. Run: gcloud auth application-default login\n"
                "  2. Pass credentials_file= pointing to your client_secrets.json\n"
                "See the tha-google-runner README for setup instructions."
            ) from None

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
            flow = InstalledAppFlow.from_client_secrets_file(str(credentials_file), _SCOPES)
            creds = flow.run_local_server(port=0)
        token.write_text(creds.to_json())

    return creds
