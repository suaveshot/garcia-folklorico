"""
Garcia Folklorico Studio -- GBP Auth Setup
One-time OAuth2 setup for Google Business Profile API.

Run once: python -m gbp.auth_setup

Prerequisites:
  - Google Cloud project with these APIs enabled:
    - My Business Account Management API
    - My Business Business Information API
    - Business Profile Performance API
  - GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET env vars set
"""

import json
import os
from pathlib import Path

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

SCRIPT_DIR = Path(__file__).parent
CONFIG_FILE = SCRIPT_DIR / "gbp_config.json"

SCOPES = [
    "https://www.googleapis.com/auth/business.manage",
]


def _load_config() -> dict:
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _build_client_config():
    return {
        "installed": {
            "client_id": os.environ["GOOGLE_CLIENT_ID"],
            "client_secret": os.environ["GOOGLE_CLIENT_SECRET"],
            "project_id": os.environ.get("GOOGLE_PROJECT_ID", "garcia-folklorico"),
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "redirect_uris": ["http://localhost"],
        }
    }


def get_credentials() -> Credentials:
    """Returns authorized credentials for GBP APIs."""
    config = _load_config()
    token_path = SCRIPT_DIR / config["token_path"]

    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_config(
                _build_client_config(), SCOPES
            )
            creds = flow.run_local_server(port=0)
        with open(token_path, "w") as f:
            f.write(creds.to_json())

    return creds


if __name__ == "__main__":
    print("=" * 60)
    print("Garcia Folklorico Studio -- GBP Auth Setup")
    print("=" * 60)
    print()
    print("Sign in with the Google account that manages")
    print("Garcia Folklorico Studio's Business Profile.")
    print()
    input("Press Enter to open browser...")
    get_credentials()
    print()
    print("Authorization complete! (gbp_token.json saved)")
    print("Next step: python -m gbp.account_fetcher --list")
