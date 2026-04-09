"""
Garcia Folklorico Studio -- Lightweight Watchdog
Monitors backend health, database, SMTP, and automation tool status.

Checks:
1. FastAPI /api/health endpoint responds
2. SQLite database file exists and is not locked
3. SMTP credentials are valid (test connection)
4. Automation tools ran recently (via health_status.json)

Sends daily digest at 8 PM. Sends immediate alert if anything is down.

Runs every 30 min via cron on VPS.

Usage:
    python -m watchdog.run_watchdog
    python -m watchdog.run_watchdog --digest   # Force send digest now
"""

import json
import logging
import smtplib
import sys
from datetime import datetime, timedelta
from pathlib import Path
from urllib.request import urlopen
from urllib.error import URLError

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from auto_config import (
    get_db, send_email_sync, SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD,
    ALERT_EMAIL, API_BASE_URL, BACKEND_DIR
)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "backend"))
from services.email import _email, _heading, _sub, _section_header, _callout, _divider

from shared_utils import report_status, cleanup_old_events

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [watchdog] %(message)s",
    handlers=[
        logging.FileHandler(Path(__file__).parent / "watchdog.log"),
        logging.StreamHandler(),
    ]
)
log = logging.getLogger(__name__)

HEALTH_FILE = Path(__file__).parent / "health_status.json"
WATCHDOG_STATE = Path(__file__).parent / "watchdog_state.json"

# How long before a tool's last_run is considered stale
STALE_THRESHOLDS = {
    "sheets_sync": timedelta(hours=1),
    "reminders": timedelta(hours=26),   # Runs daily at 4 PM
    "waitlist": timedelta(hours=4),     # Runs every 2 hours
}


def load_watchdog_state() -> dict:
    try:
        return json.loads(WATCHDOG_STATE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {"last_digest": None, "last_alert": None}


def save_watchdog_state(state: dict):
    tmp = str(WATCHDOG_STATE) + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=2, default=str)
    Path(tmp).replace(WATCHDOG_STATE)


def check_api_health() -> dict:
    """Check if the FastAPI backend is responding."""
    try:
        url = f"{API_BASE_URL}/api/health"
        with urlopen(url, timeout=10) as resp:
            if resp.status == 200:
                return {"status": "ok", "detail": "API responding"}
    except URLError as e:
        return {"status": "error", "detail": f"API unreachable: {e.reason}"}
    except Exception as e:
        return {"status": "error", "detail": f"API check failed: {e}"}
    return {"status": "error", "detail": f"API returned non-200"}


def check_database() -> dict:
    """Check that the SQLite database exists and is accessible."""
    db_path = BACKEND_DIR / "database.db"

    if not db_path.exists():
        return {"status": "error", "detail": "database.db not found"}

    try:
        db = get_db()
        # Simple query to verify DB is not locked
        from models import Block
        db.query(Block).first()
        db.close()
        size_mb = db_path.stat().st_size / (1024 * 1024)
        return {"status": "ok", "detail": f"DB accessible ({size_mb:.1f} MB)"}
    except Exception as e:
        return {"status": "error", "detail": f"DB query failed: {e}"}


def check_smtp() -> dict:
    """Test SMTP connection without sending an email."""
    if not SMTP_USER or not SMTP_PASSWORD:
        return {"status": "warning", "detail": "SMTP credentials not set"}

    try:
        if SMTP_PORT == 465:
            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=10) as server:
                server.login(SMTP_USER, SMTP_PASSWORD)
        else:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as server:
                server.starttls()
                server.login(SMTP_USER, SMTP_PASSWORD)
        return {"status": "ok", "detail": "SMTP connection successful"}
    except Exception as e:
        return {"status": "error", "detail": f"SMTP failed: {e}"}


def check_automation_health() -> dict:
    """Check that automation tools ran recently."""
    if not HEALTH_FILE.exists():
        return {"status": "warning", "detail": "No health data yet (first run?)"}

    try:
        data = json.loads(HEALTH_FILE.read_text())
    except json.JSONDecodeError:
        return {"status": "error", "detail": "health_status.json is corrupted"}

    now = datetime.now()
    issues = []
    healthy = []

    for tool, threshold in STALE_THRESHOLDS.items():
        if tool not in data:
            continue  # Tool hasn't run yet, not an issue

        entry = data[tool]
        last_run = datetime.fromisoformat(entry["last_run"])
        age = now - last_run

        if entry["status"] == "error":
            issues.append(f"{tool}: last run had error - {entry.get('detail', 'unknown')}")
        elif age > threshold:
            hours = age.total_seconds() / 3600
            issues.append(f"{tool}: stale ({hours:.1f}h since last run)")
        else:
            healthy.append(tool)

    if issues:
        return {"status": "warning", "detail": "; ".join(issues)}

    if healthy:
        return {"status": "ok", "detail": f"All tools healthy: {', '.join(healthy)}"}

    return {"status": "ok", "detail": "No automation tools have run yet"}


def run_all_checks() -> list[dict]:
    """Run all health checks and return results."""
    checks = [
        {"name": "API Health", "result": check_api_health()},
        {"name": "Database", "result": check_database()},
        {"name": "SMTP", "result": check_smtp()},
        {"name": "Automation Tools", "result": check_automation_health()},
    ]
    return checks


def build_digest_email(checks) -> tuple[str, str]:
    """Build HTML digest email from check results."""
    has_errors = any(c["result"]["status"] == "error" for c in checks)
    has_warnings = any(c["result"]["status"] == "warning" for c in checks)

    if has_errors:
        status_label = "ISSUES DETECTED"
        status_color = "#E8620A"
    elif has_warnings:
        status_label = "WARNINGS"
        status_color = "#FFB347"
    else:
        status_label = "ALL HEALTHY"
        status_color = "#2e7d32"

    subject = f"Garcia Folklorico Watchdog: {status_label}"

    c = _heading("System Health Report")
    c += _sub(f"Status: <strong style='color:{status_color}'>{status_label}</strong>")

    for check in checks:
        result = check["result"]
        icon = {"ok": "&#9679;", "warning": "&#9888;", "error": "&#10060;"}.get(result["status"], "?")
        color = {"ok": "#2e7d32", "warning": "#E8620A", "error": "#d32f2f"}.get(result["status"], "#666")

        c += (
            f'<p style="margin:8px 0;font-family:Nunito,-apple-system,sans-serif;font-size:14px;">'
            f'<span style="color:{color};font-size:16px;">{icon}</span> '
            f'<strong>{check["name"]}</strong>: '
            f'<span style="color:#8a7a6a;">{result["detail"]}</span></p>'
        )

    c += _divider()
    c += _callout(f"Checked at {datetime.now().strftime('%Y-%m-%d %I:%M %p')}")

    return subject, _email(c, f"Watchdog: {status_label}")


def main():
    force_digest = "--digest" in sys.argv
    log.info("Running watchdog checks...")

    checks = run_all_checks()
    now = datetime.now()

    for check in checks:
        status = check["result"]["status"]
        symbol = {"ok": "OK", "warning": "WARN", "error": "ERROR"}[status]
        log.info(f"  [{symbol}] {check['name']}: {check['result']['detail']}")

    has_errors = any(c["result"]["status"] == "error" for c in checks)
    has_warnings = any(c["result"]["status"] == "warning" for c in checks)

    state = load_watchdog_state()

    # Send immediate alert if there are errors
    if has_errors:
        last_alert = state.get("last_alert")
        # Don't spam: only alert once per hour
        should_alert = True
        if last_alert:
            last_dt = datetime.fromisoformat(last_alert)
            if (now - last_dt) < timedelta(hours=1):
                should_alert = False
                log.info("  Skipping alert (sent within last hour)")

        if should_alert:
            subject, html = build_digest_email(checks)
            subject = "[ALERT] " + subject
            send_email_sync(ALERT_EMAIL, subject, html)
            state["last_alert"] = now.isoformat()
            log.info(f"  Alert sent to {ALERT_EMAIL}")

    # Send daily digest at 8 PM (or on --digest flag)
    is_digest_time = 19 <= now.hour <= 20
    last_digest = state.get("last_digest")
    digest_sent_today = False
    if last_digest:
        last_dt = datetime.fromisoformat(last_digest)
        digest_sent_today = last_dt.date() == now.date()

    if force_digest or (is_digest_time and not digest_sent_today):
        subject, html = build_digest_email(checks)
        send_email_sync(ALERT_EMAIL, subject, html)
        state["last_digest"] = now.isoformat()
        log.info(f"  Daily digest sent to {ALERT_EMAIL}")

    # Cleanup old events (monthly maintenance)
    if now.day == 1 and now.hour < 1:
        deleted = cleanup_old_events(days=30)
        if deleted:
            log.info(f"  Cleaned up {deleted} old event files")

    save_watchdog_state(state)

    # Report own health
    overall = "error" if has_errors else ("warning" if has_warnings else "ok")
    detail = ", ".join(f"{c['name']}={c['result']['status']}" for c in checks)
    report_status("watchdog", overall, detail)

    log.info("Watchdog check complete")


if __name__ == "__main__":
    main()
