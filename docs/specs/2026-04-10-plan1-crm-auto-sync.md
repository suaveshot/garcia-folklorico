# CRM Auto-Sync & Email Logging - Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Garcia Folklorico CRM Google Sheet auto-update from backend events -- new registrations, cancellations, waitlist promotions, and rental bookings appear in the Student Pipeline, Revenue & Payments, and Communications Log tabs automatically.

**Architecture:** Backend routes emit JSON event files when actions occur (same file-based pattern as existing automation). A new cron job (every 5 min) reads unprocessed events and writes rows to the Google Sheet via the Sheets API. Emails sent by the system are auto-logged to the Communications Log tab.

**Tech Stack:** Python, gspread, FastAPI (existing), file-based event bus (existing pattern)

**Spec:** `docs/specs/2026-04-10-crm-automation-payments-portal-design.md` Section 1

**Google Sheet ID:** `18n5TyV36F5bbhTcfynzwWp0qbnggdsifCIfbmpOEyd0`

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `backend/services/events.py` | CREATE | Lightweight event publisher for FastAPI backend |
| `backend/routes/registration.py` | MODIFY | Emit events on register, cancel, waitlist promote |
| `backend/routes/rental.py` | MODIFY | Emit event on rental booking |
| `backend/services/email.py` | MODIFY | Emit `email_sent` event after every email |
| `automation/crm_events/__init__.py` | CREATE | Package init |
| `automation/crm_events/run_crm_events.py` | CREATE | Main cron job: read events, write to Sheets |
| `automation/crm_events/sheets_writer.py` | CREATE | Google Sheets helpers: append row, find row, update row |
| `automation/sheets_sync/run_sync.py` | MODIFY | Add GOOGLE_SHEET_ID to env loading |
| `entrypoint.sh` | MODIFY | Add crm_events cron job (every 5 min) |

---

## Task 1: Backend Event Publisher

**Files:**
- Create: `backend/services/events.py`

- [ ] **Step 1: Create the event publisher module**

This is a minimal event publisher that writes JSON files to a known directory. It mirrors the format used by `automation/shared_utils/event_bus.py` so the CRM processor can read events from both sources.

```python
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
```

Note: Unlike the automation event_bus.py (which stores one event per day per type), this uses unique filenames with microsecond timestamps so multiple events of the same type can coexist. The CRM processor reads all unprocessed files.

- [ ] **Step 2: Commit**

```bash
git add backend/services/events.py
git commit -m "feat: add backend event publisher for CRM auto-sync"
```

---

## Task 2: Emit Events from Registration Routes

**Files:**
- Modify: `backend/routes/registration.py`

- [ ] **Step 1: Add event imports and emit on registration**

At the top of `registration.py`, add the import:

```python
from services.events import publish_event
```

In the `POST /api/classes/register` handler, after the `db.commit()` and before the email sends, add:

```python
# Emit CRM event
event_type = "waitlisted" if reg.status == "waitlisted" else "created"
publish_event("registration", event_type, {
    "registration_id": reg.id,
    "parent_name": reg.parent_name,
    "child_name": reg.child_name,
    "child_age": reg.child_age,
    "phone": reg.phone,
    "email": reg.email,
    "class_name": class_type.name_en,
    "block_name": block.name,
    "status": reg.status,
    "language": reg.language,
})
```

- [ ] **Step 2: Emit on cancellation**

In the `POST /api/classes/cancel/{registration_id}` handler, after `db.commit()`, add:

```python
publish_event("registration", "cancelled", {
    "registration_id": registration_id,
    "child_name": reg.child_name,
    "parent_name": reg.parent_name,
    "class_name": class_type.name_en,
})
```

And if a waitlisted person gets promoted (the `if next_in_line:` block), add after that commit:

```python
publish_event("registration", "waitlist_promoted", {
    "registration_id": next_in_line.id,
    "child_name": next_in_line.child_name,
    "parent_name": next_in_line.parent_name,
    "class_name": class_type.name_en,
    "block_name": block.name,
})
```

- [ ] **Step 3: Emit on waitlist confirmation**

In the `POST /api/classes/confirm-waitlist/{registration_id}` handler, after `db.commit()`, add:

```python
publish_event("registration", "waitlist_confirmed", {
    "registration_id": registration_id,
    "child_name": reg.child_name,
    "parent_name": reg.parent_name,
    "class_name": class_type.name_en,
})
```

- [ ] **Step 4: Commit**

```bash
git add backend/routes/registration.py
git commit -m "feat: emit CRM events from registration routes"
```

---

## Task 3: Emit Events from Rental Routes

**Files:**
- Modify: `backend/routes/rental.py`

- [ ] **Step 1: Add event import and emit on booking**

At the top of `rental.py`, add:

```python
from services.events import publish_event
```

In the `POST /api/rentals/book` handler, after `db.commit()` and before email sends, add:

```python
publish_event("rental", "booked", {
    "booking_id": booking.id,
    "date": str(booking.date),
    "start_time": booking.start_time.strftime("%I:%M %p").lstrip("0"),
    "end_time": booking.end_time.strftime("%I:%M %p").lstrip("0"),
    "hours": booking.hours,
    "total_price": booking.total_price,
    "renter_name": booking.renter_name,
    "phone": booking.phone,
    "email": booking.email,
    "purpose": booking.purpose,
    "language": booking.language,
})
```

- [ ] **Step 2: Commit**

```bash
git add backend/routes/rental.py
git commit -m "feat: emit CRM events from rental routes"
```

---

## Task 4: Auto-Log Emails to Communications Log

**Files:**
- Modify: `backend/services/email.py`

- [ ] **Step 1: Add event import**

At the top of `email.py`, add:

```python
from services.events import publish_event
```

- [ ] **Step 2: Emit email_sent event from each email function**

In `send_registration_email()`, after the successful `await aiosmtplib.send(msg, ...)` call, add:

```python
publish_event("email", "sent", {
    "to": reg.email,
    "contact_name": reg.parent_name,
    "child_name": reg.child_name,
    "email_type": "registration_confirmation" if reg.status == "registered" else "waitlist_notification",
    "subject": subject,
    "class_name": class_type.name_en,
})
```

In `send_registration_notification()`, after successful send:

```python
publish_event("email", "sent", {
    "to": STUDIO_EMAIL,
    "contact_name": "Studio Team",
    "child_name": reg.child_name,
    "email_type": "registration_staff_notification",
    "subject": subject,
    "class_name": class_type.name_en,
})
```

In `send_waitlist_promotion_email()`, after successful send:

```python
publish_event("email", "sent", {
    "to": reg.email,
    "contact_name": reg.parent_name,
    "child_name": reg.child_name,
    "email_type": "waitlist_promotion",
    "subject": subject,
    "class_name": class_type.name_en,
})
```

In `send_rental_confirmation()`, after successful send:

```python
publish_event("email", "sent", {
    "to": booking.email,
    "contact_name": booking.renter_name,
    "child_name": "",
    "email_type": "rental_confirmation",
    "subject": subject,
    "class_name": "",
})
```

In `send_rental_notification()`, after successful send:

```python
publish_event("email", "sent", {
    "to": STUDIO_EMAIL,
    "contact_name": "Studio Team",
    "child_name": "",
    "email_type": "rental_staff_notification",
    "subject": subject,
    "class_name": "",
})
```

**Important:** Wrap each `publish_event` call in try/except so a logging failure never breaks email delivery:

```python
try:
    publish_event("email", "sent", {...})
except Exception:
    pass  # CRM logging is best-effort
```

- [ ] **Step 3: Commit**

```bash
git add backend/services/email.py
git commit -m "feat: auto-log all system emails as CRM events"
```

---

## Task 5: Google Sheets Writer Helper

**Files:**
- Create: `automation/crm_events/__init__.py`
- Create: `automation/crm_events/sheets_writer.py`

- [ ] **Step 1: Create package init**

```python
# automation/crm_events/__init__.py
```

Empty file.

- [ ] **Step 2: Create sheets_writer.py**

```python
"""
Google Sheets write helpers for CRM event processing.
Provides append_row, find_row, and update_cell operations
on the Garcia Folklorico CRM spreadsheet.
"""

import logging
import time

log = logging.getLogger(__name__)


def get_spreadsheet(gc, sheet_id):
    """Open the CRM spreadsheet by ID."""
    return gc.open_by_key(sheet_id)


def append_row(ws, row_data, value_input_option="RAW"):
    """Append a row to the bottom of a worksheet's data."""
    ws.append_row(row_data, value_input_option=value_input_option)
    time.sleep(1.5)  # Rate limiting


def find_row_by_value(ws, col_index, value, start_row=2):
    """Find the first row where column col_index matches value.

    Args:
        ws: Worksheet object
        col_index: 1-based column index to search
        value: Value to match (string comparison)
        start_row: Row to start searching from (skip header)

    Returns:
        Row number (1-based) or None if not found
    """
    col_values = ws.col_values(col_index)
    search_value = str(value)
    for i, cell_value in enumerate(col_values):
        row_num = i + 1
        if row_num < start_row:
            continue
        if str(cell_value) == search_value:
            return row_num
    return None


def update_cell(ws, row, col, value, value_input_option="RAW"):
    """Update a single cell by row and column number (1-based)."""
    ws.update_cell(row, col, value)
    time.sleep(1.0)  # Rate limiting


def update_row_cells(ws, row, updates, value_input_option="RAW"):
    """Update multiple cells in a row.

    Args:
        ws: Worksheet object
        row: Row number (1-based)
        updates: dict of {col_number: value} (1-based columns)
    """
    for col, value in updates.items():
        ws.update_cell(row, col, value)
    time.sleep(1.5)  # Rate limiting
```

- [ ] **Step 3: Commit**

```bash
git add automation/crm_events/__init__.py automation/crm_events/sheets_writer.py
git commit -m "feat: add Google Sheets write helpers for CRM events"
```

---

## Task 6: CRM Event Processor

**Files:**
- Create: `automation/crm_events/run_crm_events.py`

- [ ] **Step 1: Create the main event processor**

This is the core cron job that reads event files and writes to the CRM.

```python
"""
Garcia Folklorico Studio -- CRM Event Processor
Reads backend event files and writes rows to the Google Sheets CRM.

Processes: registrations, cancellations, waitlist promotions,
rental bookings, and email logs.

Runs every 5 minutes via cron.

Usage:
    python -m crm_events.run_crm_events
"""

import json
import logging
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from auto_config import GOOGLE_SHEETS_CREDS, GOOGLE_SHEET_ID, AUTOMATION_DIR
from shared_utils import report_status, publish_event

from crm_events.sheets_writer import (
    get_spreadsheet, append_row, find_row_by_value, update_row_cells,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [crm_events] %(message)s",
    handlers=[
        logging.FileHandler(Path(__file__).parent / "crm_events.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)

EVENTS_DIR = AUTOMATION_DIR / "pipeline_events"
PROCESSED_DIR = EVENTS_DIR / "processed"

# CRM tab column mappings (1-based)
# Student Pipeline: A=Lead ID, B=Inquiry Date, C=Parent Name, D=Child Name,
#   E=Age, F=Pipeline Stage, G=Class Interest, H=Last Contact Date,
#   I=Next Action Date, J=Contact Method, K=Phone, L=Email, M=Language,
#   N=Touch Count, O=Trial Date, P=Trial Result, Q=Reg Sent Date,
#   R=Enrollment Date, S=Block Enrolled, T=Lead Source, U=Notes, V=Days in Stage
PIPELINE_COLS = {
    "lead_id": 1, "inquiry_date": 2, "parent_name": 3, "child_name": 4,
    "age": 5, "stage": 6, "class_interest": 7, "last_contact": 8,
    "next_action": 9, "contact_method": 10, "phone": 11, "email": 12,
    "language": 13, "touch_count": 14, "trial_date": 15, "trial_result": 16,
    "reg_sent_date": 17, "enrollment_date": 18, "block": 19,
    "lead_source": 20, "notes": 21,
}

# Revenue & Payments: A=Record ID, B=Student/Renter, C=Type, D=Due Date,
#   E=Class/Service, F=Block/Period, G=Amount, H=Payment Status,
#   I=Paid Date, J=Payment Method, K=Notes
REVENUE_COLS = {
    "record_id": 1, "name": 2, "type": 3, "due_date": 4,
    "service": 5, "block": 6, "amount": 7, "payment_status": 8,
    "paid_date": 9, "payment_method": 10, "notes": 11,
}

# Communications Log: A=Log ID, B=Date/Time, C=Contact Name, D=Child Name,
#   E=Pipeline Stage, F=Touch #, G=Channel, H=Direction, I=Summary,
#   J=Response?, K=Next Action, L=Next Action Date
COMMS_COLS = {
    "log_id": 1, "datetime": 2, "contact_name": 3, "child_name": 4,
    "stage": 5, "touch_num": 6, "channel": 7, "direction": 8,
    "summary": 9, "response": 10, "next_action": 11, "next_action_date": 12,
}

# Email type to summary text mapping
EMAIL_SUMMARIES = {
    "registration_confirmation": "Registration confirmed - welcome email sent",
    "waitlist_notification": "Added to waitlist - notification sent",
    "waitlist_promotion": "Spot opened - promotion email sent with 48hr deadline",
    "registration_staff_notification": "Staff notified of new registration",
    "rental_confirmation": "Rental booking confirmed - confirmation sent",
    "rental_staff_notification": "Staff notified of new rental booking",
}


def get_unprocessed_events():
    """Get all unprocessed event files, sorted by timestamp."""
    if not EVENTS_DIR.exists():
        return []

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    events = []
    for f in sorted(EVENTS_DIR.glob("*.json")):
        if f.is_file():
            try:
                data = json.loads(f.read_text())
                events.append((f, data))
            except (json.JSONDecodeError, OSError) as e:
                log.warning(f"Skipping malformed event file {f.name}: {e}")
    return events


def mark_processed(filepath):
    """Move event file to processed directory."""
    dest = PROCESSED_DIR / filepath.name
    filepath.rename(dest)


def process_registration_created(spreadsheet, event):
    """New registration -> add to Student Pipeline + Revenue."""
    today = datetime.utcnow().strftime("%Y-%m-%d")

    # Student Pipeline row
    pipeline_ws = spreadsheet.worksheet("Student Pipeline")
    pipeline_row = [
        f"GF-{event.get('registration_id', '')}",  # Lead ID
        today,                                        # Inquiry Date
        event.get("parent_name", ""),                 # Parent Name
        event.get("child_name", ""),                  # Child Name
        event.get("child_age", ""),                   # Age
        "Enrolled",                                   # Pipeline Stage
        event.get("class_name", ""),                  # Class Interest
        today,                                        # Last Contact Date
        "",                                           # Next Action Date
        "Web Form",                                   # Contact Method
        event.get("phone", ""),                       # Phone
        event.get("email", ""),                       # Email
        event.get("language", "EN").upper(),           # Language
        "1",                                          # Touch Count
        "",                                           # Trial Date
        "",                                           # Trial Result
        "",                                           # Reg Sent Date
        today,                                        # Enrollment Date
        event.get("block_name", ""),                  # Block Enrolled
        "Website",                                    # Lead Source
        "Auto-created from website registration",     # Notes
    ]
    append_row(pipeline_ws, pipeline_row)

    # Revenue & Payments row
    revenue_ws = spreadsheet.worksheet("Revenue & Payments")
    revenue_row = [
        f"T-{event.get('registration_id', '')}",     # Record ID
        f"{event.get('parent_name', '')} ({event.get('child_name', '')})",  # Name
        "Tuition",                                    # Type
        today,                                        # Due Date
        event.get("class_name", ""),                  # Class/Service
        event.get("block_name", ""),                  # Block/Period
        "",                                           # Amount (blank - set from Settings)
        "Unpaid",                                     # Payment Status
        "",                                           # Paid Date
        "",                                           # Payment Method
        "",                                           # Notes
    ]
    append_row(revenue_ws, revenue_row)
    log.info(f"Processed registration_created: {event.get('child_name')} in {event.get('class_name')}")


def process_registration_waitlisted(spreadsheet, event):
    """Waitlisted registration -> add to Pipeline as Waitlisted."""
    today = datetime.utcnow().strftime("%Y-%m-%d")

    pipeline_ws = spreadsheet.worksheet("Student Pipeline")
    pipeline_row = [
        f"GF-{event.get('registration_id', '')}",
        today,
        event.get("parent_name", ""),
        event.get("child_name", ""),
        event.get("child_age", ""),
        "Waitlisted",
        event.get("class_name", ""),
        today,
        "",
        "Web Form",
        event.get("phone", ""),
        event.get("email", ""),
        event.get("language", "EN").upper(),
        "1",
        "", "", "", "",
        event.get("block_name", ""),
        "Website",
        "Auto-created from website registration (waitlisted)",
    ]
    append_row(pipeline_ws, pipeline_row)
    log.info(f"Processed registration_waitlisted: {event.get('child_name')}")


def process_registration_cancelled(spreadsheet, event):
    """Cancellation -> update Pipeline row to Lost, Revenue to Waived."""
    lead_id = f"GF-{event.get('registration_id', '')}"

    pipeline_ws = spreadsheet.worksheet("Student Pipeline")
    row = find_row_by_value(pipeline_ws, 1, lead_id)
    if row:
        update_row_cells(pipeline_ws, row, {
            PIPELINE_COLS["stage"]: "Lost",
            PIPELINE_COLS["notes"]: "Cancelled by parent",
            PIPELINE_COLS["last_contact"]: datetime.utcnow().strftime("%Y-%m-%d"),
        })

    record_id = f"T-{event.get('registration_id', '')}"
    revenue_ws = spreadsheet.worksheet("Revenue & Payments")
    rev_row = find_row_by_value(revenue_ws, 1, record_id)
    if rev_row:
        update_row_cells(revenue_ws, rev_row, {
            REVENUE_COLS["payment_status"]: "Waived",
            REVENUE_COLS["notes"]: "Cancelled",
        })

    log.info(f"Processed registration_cancelled: {lead_id}")


def process_waitlist_promoted(spreadsheet, event):
    """Waitlist promotion -> update Pipeline row to Enrolled."""
    lead_id = f"GF-{event.get('registration_id', '')}"
    today = datetime.utcnow().strftime("%Y-%m-%d")

    pipeline_ws = spreadsheet.worksheet("Student Pipeline")
    row = find_row_by_value(pipeline_ws, 1, lead_id)
    if row:
        update_row_cells(pipeline_ws, row, {
            PIPELINE_COLS["stage"]: "Enrolled",
            PIPELINE_COLS["enrollment_date"]: today,
            PIPELINE_COLS["last_contact"]: today,
            PIPELINE_COLS["notes"]: "Promoted from waitlist",
        })

    # Also create a Revenue row for the now-enrolled student
    revenue_ws = spreadsheet.worksheet("Revenue & Payments")
    revenue_row = [
        f"T-{event.get('registration_id', '')}",
        f"{event.get('parent_name', '')} ({event.get('child_name', '')})",
        "Tuition",
        today,
        event.get("class_name", ""),
        event.get("block_name", ""),
        "",
        "Unpaid",
        "", "", "",
    ]
    append_row(revenue_ws, revenue_row)
    log.info(f"Processed waitlist_promoted: {lead_id}")


def process_rental_booked(spreadsheet, event):
    """Rental booking -> add to Revenue & Payments."""
    revenue_ws = spreadsheet.worksheet("Revenue & Payments")
    revenue_row = [
        f"R-{event.get('booking_id', '')}",
        event.get("renter_name", ""),
        "Rental",
        event.get("date", ""),
        f"Studio Rental ({event.get('hours', '')}hrs)",
        "",
        event.get("total_price", ""),
        "Unpaid",
        "",
        "",
        f"{event.get('purpose', '')} | {event.get('start_time', '')}-{event.get('end_time', '')}",
    ]
    append_row(revenue_ws, revenue_row)
    log.info(f"Processed rental_booked: {event.get('renter_name')} on {event.get('date')}")


def process_email_sent(spreadsheet, event):
    """Email sent -> add to Communications Log."""
    email_type = event.get("email_type", "")

    # Skip staff notifications from comms log (internal)
    if email_type.endswith("_staff_notification"):
        return

    comms_ws = spreadsheet.worksheet("Communications Log")
    summary = EMAIL_SUMMARIES.get(email_type, f"Email sent: {email_type}")

    comms_row = [
        "",                                           # Log ID (formula in sheet)
        event.get("published_at", "")[:16].replace("T", " "),  # Date/Time
        event.get("contact_name", ""),                # Contact Name
        event.get("child_name", ""),                  # Child Name
        "",                                           # Pipeline Stage (manual)
        "1",                                          # Touch #
        "Email",                                      # Channel
        "Outbound",                                   # Direction
        summary,                                      # Summary
        "N/A",                                        # Response?
        "",                                           # Next Action
        "",                                           # Next Action Date
    ]
    append_row(comms_ws, comms_row)
    log.info(f"Logged email: {email_type} to {event.get('to', '')}")


# Event type -> handler mapping
EVENT_HANDLERS = {
    ("registration", "created"): process_registration_created,
    ("registration", "waitlisted"): process_registration_waitlisted,
    ("registration", "cancelled"): process_registration_cancelled,
    ("registration", "waitlist_promoted"): process_waitlist_promoted,
    ("registration", "waitlist_confirmed"): process_waitlist_promoted,  # Same action
    ("rental", "booked"): process_rental_booked,
    ("email", "sent"): process_email_sent,
}


def main():
    log.info("Starting CRM event processing...")

    if not GOOGLE_SHEETS_CREDS or not GOOGLE_SHEET_ID:
        log.warning("Google Sheets not configured. Set GOOGLE_SHEETS_CREDS and GOOGLE_SHEET_ID.")
        report_status("crm_events", "warning", "Google Sheets not configured")
        return

    try:
        import gspread
        gc = gspread.service_account(filename=GOOGLE_SHEETS_CREDS)
        spreadsheet = gc.open_by_key(GOOGLE_SHEET_ID)
    except Exception as e:
        log.error(f"Failed to connect to Google Sheets: {e}")
        report_status("crm_events", "error", str(e))
        return

    events = get_unprocessed_events()
    if not events:
        log.info("No events to process.")
        report_status("crm_events", "ok", "No events", metrics={"processed": 0})
        return

    processed = 0
    errors = 0

    for filepath, event in events:
        pipeline = event.get("pipeline", "")
        event_type = event.get("event_type", "")
        handler_key = (pipeline, event_type)

        handler = EVENT_HANDLERS.get(handler_key)
        if not handler:
            log.debug(f"No handler for {pipeline}/{event_type}, skipping")
            mark_processed(filepath)
            continue

        try:
            handler(spreadsheet, event)
            mark_processed(filepath)
            processed += 1
        except Exception as e:
            log.error(f"Error processing {filepath.name}: {e}", exc_info=True)
            errors += 1

    metrics = {"processed": processed, "errors": errors, "total": len(events)}
    status = "ok" if errors == 0 else "warning"
    detail = f"{processed} processed, {errors} errors"

    report_status("crm_events", status, detail, metrics=metrics)
    publish_event("crm_events", "processed", metrics)
    log.info(f"Done: {detail}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Commit**

```bash
git add automation/crm_events/__init__.py automation/crm_events/run_crm_events.py
git commit -m "feat: add CRM event processor cron job"
```

---

## Task 7: Update Entrypoint for New Cron Job

**Files:**
- Modify: `entrypoint.sh`

- [ ] **Step 1: Add crm_events cron job**

Add this line to the crontab section in `entrypoint.sh`, alongside the existing cron jobs:

```bash
*/5 * * * * cd /app/automation && python -m crm_events.run_crm_events >> /var/log/garcia-crm-events.log 2>&1
```

Also add the sheets_sync cron job if not already present:

```bash
*/15 * * * * cd /app/automation && python -m sheets_sync.run_sync >> /var/log/garcia-sheets-sync.log 2>&1
```

- [ ] **Step 2: Commit**

```bash
git add entrypoint.sh
git commit -m "feat: add crm_events and sheets_sync cron jobs"
```

---

## Task 8: Push and Deploy

- [ ] **Step 1: Push all changes to GitHub**

```bash
git push origin main
```

- [ ] **Step 2: Redeploy to VPS via Hostinger API**

Use `VPS_createNewProjectV1` with:
- `project_name`: garcia-folklorico
- `content`: https://github.com/suaveshot/garcia-folklorico
- `environment`: existing env vars + `GOOGLE_SHEETS_CREDS` and `GOOGLE_SHEET_ID`

- [ ] **Step 3: Verify deployment**

Check project status via `VPS_getProjectListV1`. Verify app container is healthy.

---

## Verification

After deployment, test the full flow:

1. **Register a student** on the website (or via API): `POST /api/classes/register`
2. **Check pipeline_events/** directory: should have `registration_created_*.json` and `email_sent_*.json` files
3. **Wait 5 minutes** for the crm_events cron to run
4. **Open the CRM sheet**: Student Pipeline should have a new row, Revenue & Payments should have an Unpaid tuition row, Communications Log should have the email entry
5. **Cancel the registration** via API: `POST /api/classes/cancel/{id}`
6. **Wait 5 minutes**: Pipeline row should show "Lost", Revenue row should show "Waived"
7. **Book a rental** via API: `POST /api/rentals/book`
8. **Wait 5 minutes**: Revenue & Payments should have a new Rental row
