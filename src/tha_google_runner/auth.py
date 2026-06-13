from __future__ import annotations

from pathlib import Path

import google.auth
import google.auth.exceptions
import gspread

from tha_google_runner.errors import GoogleError

_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

_DEFAULT_TOKEN = Path.home() / ".config" / "tha-google-runner" / "token.json"


def build_client(
    credentials_file: str | None,
    token_file: str | None,
) -> gspread.Client:
    """Build a gspread client using ADC or an OAuth2 client_secrets.json file.

    Auth priority:
    1. Application Default Credentials (ADC) — if credentials_file is None.
       Run `gcloud auth application-default login` once to set this up.
    2. OAuth2 user flow — if credentials_file points to a client_secrets.json.
       A browser window opens on first run; the token is cached for subsequent runs.
    """
    if credentials_file is None:
        try:
            creds, _ = google.auth.default(scopes=_SCOPES)
            return gspread.Client(auth=creds)
        except google.auth.exceptions.DefaultCredentialsError:
            raise GoogleError(
                "No Google credentials found. Either:\n"
                "  1. Run: gcloud auth application-default login\n"
                "  2. Pass credentials_file= pointing to your client_secrets.json\n"
                "See the tha-google-runner README for setup instructions."
            ) from None

    token = token_file or str(_DEFAULT_TOKEN)
    Path(token).parent.mkdir(parents=True, exist_ok=True)
    return gspread.oauth(
        credentials_filename=credentials_file,
        authorized_user_filename=token,
    )
