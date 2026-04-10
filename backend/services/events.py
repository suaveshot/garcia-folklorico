"""
Lightweight event publisher for the FastAPI backend.
Writes JSON event files that automation cron jobs pick up.
"""

import json
import os
from datetime import datetime
from pathlib import Path

# Event directory: /app/automation/pipeline_events/ in Docker,
# or relative to backend dir locally
EVENTS_DIR = Path(os.getenv(
    "EVENTS_DIR",
    str(Path(__file__).resolve().parent.parent.parent / "automation" / "pipeline_events")
))


def publish_event(pipeline: str, event_type: str, data: dict) -> Path:
    """Write an event file for automation tools to process.

    Args:
        pipeline: Source pipeline name (e.g., "registration", "rental")
        event_type: Event type (e.g., "created", "cancelled")
        data: Event payload dict

    Returns:
        Path to the created event file
    """
    EVENTS_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.utcnow()
    event = {
        "pipeline": pipeline,
        "event_type": event_type,
        "published_at": timestamp.isoformat(),
        **data,
    }

    # Use microsecond timestamp to avoid collisions
    filename = f"{pipeline}_{event_type}_{timestamp.strftime('%Y%m%d_%H%M%S_%f')}.json"
    filepath = EVENTS_DIR / filename

    tmp = str(filepath) + ".tmp"
    with open(tmp, "w") as f:
        json.dump(event, f, indent=2, default=str)
    Path(tmp).replace(filepath)

    return filepath
