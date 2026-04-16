"""
Garcia Folklorico Studio -- Review Engine
Sends bilingual review request emails to class parents and rental clients.

Runs daily at 10 AM via cron.

Usage:
    python -m review_engine.run_reviews             # Normal run
    python -m review_engine.run_reviews --check      # Show eligible without sending
    python -m review_engine.run_reviews --dry-run    # Generate emails without sending
"""

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from auto_config import get_db

from shared_utils import report_status, publish_event

from .eligibility import find_all_eligible, load_state, save_state
from .sender import send_review_request

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [review_engine] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(Path(__file__).parent / "review_engine.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("review_engine")

MAX_REQUESTS_PER_RUN = 20


def run_check():
    """Dry run: show who's eligible without sending."""
    log.info("=== Review Engine -- CHECK MODE ===")
    db = get_db()
    try:
        eligible, state = find_all_eligible(db)
    finally:
        db.close()

    if not eligible:
        log.info("No one eligible for review requests right now.")
        return 0

    log.info("%d person(s) eligible:", len(eligible))
    for e in eligible:
        if e["type"] == "class":
            log.info("  [class] %s (%s) -- %s / %s",
                     e["parent_name"], e["email"], e["class_name_en"], e["block_name"])
        else:
            log.info("  [rental] %s (%s) -- rental on %s",
                     e["renter_name"], e["email"], e["rental_date"])

    return len(eligible)


def run(dry_run: bool = False):
    """Normal run: check eligibility and send/draft review requests."""
    mode = "DRY RUN" if dry_run else "SEND"
    log.info("=== Review Engine -- %s MODE ===", mode)

    db = get_db()
    try:
        eligible, state = find_all_eligible(db)
    finally:
        db.close()

    if not eligible:
        log.info("No one eligible for review requests this run.")
        report_status("review_engine", "ok", "No eligible recipients", metrics={"sent": 0})
        publish_event("review_engine", "run_complete", {"eligible": 0, "sent": 0})
        return 0

    # Cap per run
    if len(eligible) > MAX_REQUESTS_PER_RUN:
        log.info("Capping at %d requests (had %d eligible)", MAX_REQUESTS_PER_RUN, len(eligible))
        eligible = eligible[:MAX_REQUESTS_PER_RUN]

    sent = 0
    errors = []

    for entry in eligible:
        try:
            result = send_review_request(entry, dry_run=dry_run)
            log.info("%s: %s -> %s", result["mode"], result["to"], result["subject"][:60])

            if result["mode"] != "failed":
                sent += 1
                # Update state
                state.setdefault("requests", {})[entry["email"]] = {
                    "last_asked": datetime.now().isoformat(),
                    "times_asked": state.get("requests", {}).get(entry["email"], {}).get("times_asked", 0) + 1,
                    "trigger_type": entry["type"],
                }
            else:
                errors.append(entry["email"])
        except Exception as e:
            log.error("Failed for %s: %s", entry["email"], e)
            errors.append(entry["email"])

    save_state(state)

    # Health reporting
    detail = f"{sent} review request(s) {'previewed' if dry_run else 'sent'}"
    if errors:
        detail += f", {len(errors)} error(s)"
    status = "ok" if not errors else ("warning" if sent > 0 else "error")

    report_status("review_engine", status, detail, metrics={
        "eligible": len(eligible),
        "sent": sent,
        "errors": len(errors),
    })
    publish_event("review_engine", "run_complete", {
        "eligible": len(eligible),
        "sent": sent,
        "mode": mode,
    })

    log.info("=== Review Engine complete: %s ===", detail)
    return sent


def main():
    parser = argparse.ArgumentParser(description="Garcia Folklorico Review Engine")
    parser.add_argument("--check", action="store_true", help="Show eligible without sending")
    parser.add_argument("--dry-run", action="store_true", help="Generate emails without sending")
    args = parser.parse_args()

    try:
        if args.check:
            run_check()
        else:
            run(dry_run=args.dry_run)
    except Exception as e:
        log.exception("Review Engine failed: %s", e)
        report_status("review_engine", "error", str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()
