"""
Garcia Folklorico Studio -- Health Reporter
Each automation tool calls report_status() to track its run outcome.

Usage:
    from shared_utils import report_status

    report_status("reminders", "ok", "Sent 12 reminders",
                  metrics={"sent": 12, "skipped": 2})
"""

import json
import os
from datetime import datetime
from pathlib import Path

HEALTH_FILE = str(Path(__file__).resolve().parent.parent / "watchdog" / "health_status.json")


def report_status(pipeline: str, status: str, detail: str = "", metrics: dict = None):
    """
    Write pipeline run outcome to watchdog/health_status.json.

    Args:
        pipeline: Tool ID (e.g. 'reminders', 'sheets_sync', 'waitlist')
        status:   'ok', 'warning', or 'error'
        detail:   One-line summary
        metrics:  Optional dict of counts/values
    """
    os.makedirs(os.path.dirname(HEALTH_FILE), exist_ok=True)

    try:
        with open(HEALTH_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        data = {}

    data[pipeline] = {
        "status": status,
        "detail": detail,
        "last_run": datetime.now().isoformat(),
        "metrics": metrics or {},
    }

    tmp = HEALTH_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)
    os.replace(tmp, HEALTH_FILE)
