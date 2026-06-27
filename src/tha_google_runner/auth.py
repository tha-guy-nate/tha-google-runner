from __future__ import annotations

import json
import sys
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

# Scope constants — import and combine these to request exactly what your script needs.
SCOPE_SPREADSHEETS = "https://www.googleapis.com/auth/spreadsheets"
SCOPE_DOCUMENTS = "https://www.googleapis.com/auth/documents"
SCOPE_DRIVE = "https://www.googleapis.com/auth/drive"
SCOPE_DRIVE_READONLY = "https://www.googleapis.com/auth/drive.readonly"
SCOPE_PRESENTATIONS_READONLY = "https://www.googleapis.com/auth/presentations.readonly"
SCOPE_GMAIL_SEND = "https://www.googleapis.com/auth/gmail.send"
SCOPE_GMAIL_READONLY = "https://www.googleapis.com/auth/gmail.readonly"

# Minimal default used when no scopes= argument is passed to build_credentials().
# Does not include Gmail (opt-in via ThaGmail or explicit scopes=) or full Drive write.
_DEFAULT_SCOPES = [SCOPE_SPREADSHEETS, SCOPE_DOCUMENTS, SCOPE_DRIVE_READONLY]

# Scopes requested by tha-google-init. Covers all read + non-destructive operations.
# SCOPE_DRIVE (full write) is intentionally excluded — it is added automatically on
# first use of ThaSheets.share() / .delete() via the scope-union re-auth logic.
_FULL_SCOPES = [
    SCOPE_SPREADSHEETS,
    SCOPE_DOCUMENTS,
    SCOPE_DRIVE_READONLY,
    SCOPE_PRESENTATIONS_READONLY,
    SCOPE_GMAIL_SEND,
    SCOPE_GMAIL_READONLY,
]


def build_credentials(
    credentials_file: str | None,
    token_file: str | None,
    scopes: list[str] | None = None,
) -> google.auth.credentials.Credentials:
    """Return Google credentials.

    Priority:
    1. credentials_file arg — explicit path to client_secrets.json
    2. Standard location — <user config dir>/tha-google-runner/client_secret.json
    3. ADC — fallback; cannot access private Docs/Drive (gcloud blocks those scopes)
    """
    resolved_scopes = scopes if scopes is not None else _DEFAULT_SCOPES
    resolved_file: str | None = credentials_file
    if resolved_file is None and _DEFAULT_CLIENT_SECRET.exists():
        resolved_file = str(_DEFAULT_CLIENT_SECRET)

    if resolved_file is not None:
        return _oauth_credentials(resolved_file, token_file, resolved_scopes)

    try:
        adc_creds, _ = google.auth.default(scopes=resolved_scopes)
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
    scopes: list[str],
) -> google.auth.credentials.Credentials:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    token = Path(token_file or str(_DEFAULT_TOKEN))
    token.parent.mkdir(parents=True, exist_ok=True)

    effective_scopes = list(scopes)
    creds: Credentials | None = None
    if token.exists():
        data = json.loads(token.read_text())
        token_scopes = set(data.get("scopes") or [])
        requested_set = set(scopes)
        if token_scopes and not requested_set.issubset(token_scopes):
            # Token is missing needed scopes — expand to the union so previously-
            # consented scopes are not silently dropped on the next re-auth.
            effective_scopes = list(requested_set | token_scopes)
        creds = Credentials.from_authorized_user_info(data, effective_scopes)  # type: ignore[no-untyped-call]

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())  # type: ignore[no-untyped-call]
        else:
            flow = InstalledAppFlow.from_client_secrets_file(credentials_file, effective_scopes)
            creds = flow.run_local_server(port=0)
        token.write_text(creds.to_json())
        if sys.platform != "win32":
            token.chmod(0o600)

    return creds
