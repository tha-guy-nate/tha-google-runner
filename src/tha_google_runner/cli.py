from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path


def init() -> None:
    parser = argparse.ArgumentParser(
        prog="tha-google-init",
        description=(
            "Set up tha-google-runner credentials. Creates the config directory, "
            "optionally installs your client_secret.json, then runs the OAuth flow "
            "to mint a token."
        ),
    )
    parser.add_argument(
        "--client-secret",
        metavar="PATH",
        help="Path to the client_secret_*.json downloaded from the GCP console.",
    )
    parser.add_argument(
        "--scope",
        action="append",
        dest="scopes",
        metavar="URL",
        help=(
            "Add a scope URL to request (can be repeated). "
            "Defaults to all scopes (spreadsheets, docs, drive, slides, gmail). "
            "Example: --scope https://www.googleapis.com/auth/spreadsheets"
        ),
    )
    args = parser.parse_args()

    from tha_google_runner.auth import (
        _CONFIG_DIR,
        _DEFAULT_CLIENT_SECRET,
        _DEFAULT_TOKEN,
        _FULL_SCOPES,
    )

    scopes = args.scopes if args.scopes else list(_FULL_SCOPES)

    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Config directory: {_CONFIG_DIR}")

    if args.client_secret:
        src = Path(args.client_secret)
        if not src.exists():
            print(f"Error: file not found: {src}")
            raise SystemExit(1)
        shutil.copy(src, _DEFAULT_CLIENT_SECRET)
        print(f"Copied {src.name} → {_DEFAULT_CLIENT_SECRET}")

    if not _DEFAULT_CLIENT_SECRET.exists():
        print(
            f"\nNo client_secret.json found at:\n  {_DEFAULT_CLIENT_SECRET}\n\n"
            "Download your OAuth client secret from the GCP console and re-run:\n"
            f"  tha-google-init --client-secret <path/to/downloaded.json>"
        )
        raise SystemExit(1)

    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    creds: Credentials | None = None
    if _DEFAULT_TOKEN.exists():
        creds = Credentials.from_authorized_user_info(
            json.loads(_DEFAULT_TOKEN.read_text()), scopes
        )

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(_DEFAULT_CLIENT_SECRET), scopes)
            creds = flow.run_local_server(port=0)
        _DEFAULT_TOKEN.write_text(creds.to_json())
        if sys.platform != "win32":
            _DEFAULT_TOKEN.chmod(0o600)

    print(f"Token saved to {_DEFAULT_TOKEN}")
    print("Setup complete — ThaDocs(), ThaSheets(), and ThaDrive() work without arguments.")
