"""
Garcia Folklorico Studio -- Weekly GBP Automation
Generates and publishes a bilingual "What's New" post to Google Business Profile.

Runs every Monday at 9 AM via cron.

Usage:
    python -m gbp.run_gbp
    python -m gbp.run_gbp --dry-run
"""

import argparse
import json
import logging
import sys
import traceback
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from auto_config import send_email_sync, STUDIO_EMAIL, ALERT_EMAIL

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "backend"))
from services.email import (
    _email, _heading, _sub, _section_header, _detail_table, _detail_row,
    _callout, _divider,
)

from shared_utils import report_status, publish_event

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [gbp] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(Path(__file__).parent / "gbp.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("gbp")

SCRIPT_DIR = Path(__file__).parent
CONFIG_FILE = SCRIPT_DIR / "gbp_config.json"
STATE_FILE = SCRIPT_DIR / "gbp_state.json"


def _load_config() -> dict:
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_state() -> dict:
    if STATE_FILE.exists():
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "last_run": None,
        "runs_completed": 0,
        "post_topic_index": 0,
        "last_post": {"subject": None, "type": None, "gbp_post_name": None, "created_at": None},
    }


def _save_state(state: dict):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def _pick_topic(config: dict, state: dict) -> tuple:
    """Returns (topic_dict, next_index). Priority queue first, then round-robin."""
    priority = config.get("priority_post_topics", [])
    if priority:
        topic = priority.pop(0)
        config["priority_post_topics"] = priority
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
        log.info("Topic (priority): %s", topic.get("subject", ""))
        return topic, state.get("post_topic_index", 0)

    topics = config.get("post_topics", [])
    if not topics:
        fallback = {"type": "registration", "subject": "folklorico dance classes Oxnard CA"}
        return fallback, 0

    idx = state.get("post_topic_index", 0) % len(topics)
    topic = topics[idx]
    log.info("Topic (rotation %d/%d): %s", idx + 1, len(topics), topic.get("subject", ""))
    return topic, (idx + 1) % len(topics)


def _send_digest(topic: dict, post_summary: str, post_name: str, errors: list):
    """Send weekly digest email to Itzel + Sam."""
    c = _heading("GBP Weekly Digest")
    c += _sub(f"Week of {datetime.now().strftime('%B %d, %Y')}")

    if post_summary:
        c += _section_header("Post Published / Publicacion")
        c += _callout(post_summary[:500], "#2e7d32", "#f0f8f0")
        c += _detail_table(
            _detail_row("Topic", topic.get("subject", "")),
            _detail_row("Type", topic.get("type", "")),
        )
        if post_name:
            c += f'<p style="font-size:12px;color:#8a7a6a;">GBP ref: {post_name}</p>'
    else:
        c += _callout("No post generated this week.", "#E8620A")

    if errors:
        c += _section_header("Warnings")
        for err in errors:
            c += f'<p style="font-size:13px;color:#c62828;">{err}</p>'

    html = _email(c, preheader="Garcia Folklorico GBP Weekly Update")
    subject = f"GBP Weekly Digest -- {datetime.now().strftime('%b %d')} | Garcia Folklorico"

    for to in [r for r in [STUDIO_EMAIL, ALERT_EMAIL] if r]:
        send_email_sync(to, subject, html)


def run(dry_run: bool = False):
    """Main GBP pipeline."""
    log.info("=" * 60)
    log.info("GBP Automation - Starting%s", "  [DRY RUN]" if dry_run else "")
    log.info("=" * 60)

    errors = []
    state = _load_state()

    try:
        config = _load_config()
    except FileNotFoundError:
        log.error("gbp_config.json not found.")
        report_status("gbp", "error", "gbp_config.json missing")
        return False

    # Check if account IDs are configured
    account_id = config.get("account_id", "").strip()
    location_id = config.get("location_id", "").strip()

    if not account_id or not location_id:
        log.warning("account_id or location_id not set. Skipping post publish.")
        log.warning("Run: python -m gbp.account_fetcher --list")
        errors.append("GBP account/location IDs not configured yet")

    # Pick topic
    log.info("Selecting post topic...")
    topic, next_idx = _pick_topic(config, state)

    # Generate post
    log.info("Generating GBP post via Claude...")
    post_summary = ""
    post_name = None

    try:
        from .post_generator import generate_post
        result = generate_post(topic)
        post_summary = result.get("summary", "")
        log.info("Post generated (%d chars): %s...", len(post_summary), post_summary[:80])
    except Exception as e:
        log.error("Post generation failed: %s", e)
        errors.append(f"Post generation error: {e}")
        traceback.print_exc()

    # Publish post
    if post_summary and account_id and location_id and not dry_run:
        log.info("Publishing post to GBP...")
        try:
            from .post_publisher import create_whats_new_post
            post_name = create_whats_new_post(post_summary, log=lambda m: log.info(m))
        except Exception as e:
            log.error("Post publish failed: %s", e)
            errors.append(f"Post publish error: {e}")
            traceback.print_exc()
    elif dry_run and post_summary:
        log.info("[DRY RUN] Post preview:\n%s", post_summary)
    elif not post_summary:
        log.info("Skipping publish -- no post content generated.")
    else:
        log.info("Skipping publish -- account IDs not configured.")

    # Send digest email
    if not dry_run:
        log.info("Sending weekly digest email...")
        try:
            _send_digest(topic, post_summary, post_name, errors)
        except Exception as e:
            log.error("Digest email failed: %s", e)

    # Save state
    state["last_run"] = datetime.now().isoformat()
    state["runs_completed"] = state.get("runs_completed", 0) + 1
    state["post_topic_index"] = next_idx
    if post_name:
        state["last_post"] = {
            "subject": topic.get("subject", ""),
            "type": topic.get("type", ""),
            "gbp_post_name": post_name,
            "created_at": datetime.now().isoformat(),
        }
    _save_state(state)

    # Health + event bus
    status = "ok" if not errors else "warning"
    report_status("gbp", status, f"Run #{state['runs_completed']}", metrics={
        "post_generated": bool(post_summary),
        "post_published": bool(post_name),
        "errors": len(errors),
    })
    publish_event("gbp", "run_complete", {
        "post_summary": post_summary[:200] if post_summary else "",
        "topic_type": topic.get("type", ""),
        "topic_subject": topic.get("subject", ""),
        "published": bool(post_name),
    })

    log.info("=" * 60)
    log.info("GBP Automation complete. Run #%d.", state["runs_completed"])
    if errors:
        log.info("%d non-fatal warning(s).", len(errors))
    log.info("=" * 60)
    return True


def main():
    parser = argparse.ArgumentParser(description="Garcia Folklorico GBP Automation")
    parser.add_argument("--dry-run", action="store_true",
                        help="Generate post without publishing or emailing")
    args = parser.parse_args()

    try:
        success = run(dry_run=args.dry_run)
        sys.exit(0 if success else 1)
    except Exception as e:
        log.exception("GBP Automation failed: %s", e)
        report_status("gbp", "error", str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()
