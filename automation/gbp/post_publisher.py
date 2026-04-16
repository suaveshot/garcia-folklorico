"""
Garcia Folklorico Studio -- GBP Post Publisher
Creates "What's New" posts on Google Business Profile.

Uses the legacy v4 Posts API (mybusiness.googleapis.com/v4).
The newer Business Information API does not handle posts.
"""

import json
from pathlib import Path

from google.auth.transport.requests import AuthorizedSession

from .auth_setup import get_credentials

SCRIPT_DIR = Path(__file__).parent
CONFIG_FILE = SCRIPT_DIR / "gbp_config.json"
POSTS_BASE_URL = "https://mybusiness.googleapis.com/v4"


def _load_config() -> dict:
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _authed_session() -> AuthorizedSession:
    return AuthorizedSession(get_credentials())


def create_whats_new_post(summary: str, log=None) -> str:
    """
    Publishes a What's New post to GBP.
    Returns the post resource name.
    """
    config = _load_config()
    account_id = config.get("account_id", "").strip()
    location_id = config.get("location_id", "").strip()
    cta_url = config.get("post_cta_url", "https://garciafolklorico.com")

    if not account_id or not location_id:
        raise ValueError(
            "account_id or location_id not set in gbp_config.json. "
            "Run: python -m gbp.account_fetcher --list"
        )

    # Enforce 1500-char GBP limit
    if len(summary) > 1500:
        summary = summary[:1497] + "..."

    payload = {
        "languageCode": "en-US",
        "summary": summary,
        "callToAction": {
            "actionType": "LEARN_MORE",
            "url": cta_url,
        },
        "topicType": "STANDARD",
    }

    session = _authed_session()
    location_path = f"{account_id}/{location_id}"
    url = f"{POSTS_BASE_URL}/{location_path}/localPosts"
    resp = session.post(url, json=payload)

    if resp.status_code not in (200, 201):
        raise RuntimeError(
            f"GBP post publish failed: HTTP {resp.status_code} -- {resp.text[:400]}"
        )

    post_name = resp.json().get("name", "")
    if log:
        log(f"GBP post published: {post_name}")
    return post_name
