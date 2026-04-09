"""
Garcia Folklorico Studio -- Pipeline Event Bus
Lightweight file-based event system for inter-tool communication.

Usage:
    from shared_utils import publish_event, read_latest_event

    publish_event("reminders", "sent", {"count": 12})
    event = read_latest_event("sheets_sync", "synced")
"""

import json
import glob
from datetime import datetime, timedelta
from pathlib import Path

EVENTS_DIR = Path(__file__).resolve().parent.parent / "pipeline_events"


def publish_event(pipeline: str, event_type: str, data: dict) -> Path:
    """Write an event file. Returns path to created file."""
    EVENTS_DIR.mkdir(exist_ok=True)

    today = datetime.now().strftime("%Y%m%d")
    filename = f"{pipeline}_{event_type}_{today}.json"
    filepath = EVENTS_DIR / filename

    event = {
        "pipeline": pipeline,
        "event_type": event_type,
        "published_at": datetime.now().isoformat(),
        **data,
    }

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(event, f, indent=2, default=str)

    return filepath


def read_latest_event(pipeline: str, event_type: str) -> dict | None:
    """Read the most recent event matching pipeline + type."""
    pattern = str(EVENTS_DIR / f"{pipeline}_{event_type}_*.json")
    files = sorted(glob.glob(pattern), reverse=True)

    if not files:
        return None

    with open(files[0], "r", encoding="utf-8") as f:
        return json.load(f)


def read_events_since(pipeline: str, event_type: str, days: int = 7) -> list[dict]:
    """Read all matching events from the last N days, newest first."""
    pattern = str(EVENTS_DIR / f"{pipeline}_{event_type}_*.json")
    files = sorted(glob.glob(pattern), reverse=True)

    cutoff = datetime.now() - timedelta(days=days)
    results = []

    for filepath in files:
        stem = Path(filepath).stem
        date_str = stem.rsplit("_", 1)[-1]
        try:
            file_date = datetime.strptime(date_str, "%Y%m%d")
        except ValueError:
            continue

        if file_date < cutoff:
            break

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                results.append(json.load(f))
        except (json.JSONDecodeError, OSError):
            continue

    return results


def cleanup_old_events(days: int = 30) -> int:
    """Delete event files older than N days. Returns count deleted."""
    if not EVENTS_DIR.exists():
        return 0

    cutoff = datetime.now() - timedelta(days=days)
    deleted = 0

    for filepath in EVENTS_DIR.glob("*.json"):
        stem = filepath.stem
        date_str = stem.rsplit("_", 1)[-1]
        try:
            file_date = datetime.strptime(date_str, "%Y%m%d")
        except ValueError:
            continue

        if file_date < cutoff:
            filepath.unlink()
            deleted += 1

    return deleted
