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

PIPELINE_COLS = {
    "lead_id": 1, "inquiry_date": 2, "parent_name": 3, "child_name": 4,
    "age": 5, "stage": 6, "class_interest": 7, "last_contact": 8,
    "next_action": 9, "contact_method": 10, "phone": 11, "email": 12,
    "language": 13, "touch_count": 14, "trial_date": 15, "trial_result": 16,
    "reg_sent_date": 17, "enrollment_date": 18, "block": 19,
    "lead_source": 20, "notes": 21,
}

REVENUE_COLS = {
    "record_id": 1, "name": 2, "type": 3, "due_date": 4,
    "service": 5, "block": 6, "amount": 7, "payment_status": 8,
    "paid_date": 9, "payment_method": 10, "notes": 11,
}

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

    pipeline_ws = spreadsheet.worksheet("Student Pipeline")
    pipeline_row = [
        f"GF-{event.get('registration_id', '')}",
        today,
        event.get("parent_name", ""),
        event.get("child_name", ""),
        event.get("child_age", ""),
        "Enrolled",
        event.get("class_name", ""),
        today,
        "",
        "Web Form",
        event.get("phone", ""),
        event.get("email", ""),
        event.get("language", "EN").upper(),
        "1",
        "", "", "",
        today,
        event.get("block_name", ""),
        "Website",
        "Auto-created from website registration",
    ]
    append_row(pipeline_ws, pipeline_row)

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

    if email_type.endswith("_staff_notification"):
        return

    comms_ws = spreadsheet.worksheet("Communications Log")
    summary = EMAIL_SUMMARIES.get(email_type, f"Email sent: {email_type}")

    comms_row = [
        "",
        event.get("published_at", "")[:16].replace("T", " "),
        event.get("contact_name", ""),
        event.get("child_name", ""),
        "",
        "1",
        "Email",
        "Outbound",
        summary,
        "N/A",
        "",
        "",
    ]
    append_row(comms_ws, comms_row)
    log.info(f"Logged email: {email_type} to {event.get('to', '')}")


EVENT_HANDLERS = {
    ("registration", "created"): process_registration_created,
    ("registration", "waitlisted"): process_registration_waitlisted,
    ("registration", "cancelled"): process_registration_cancelled,
    ("registration", "waitlist_promoted"): process_waitlist_promoted,
    ("registration", "waitlist_confirmed"): process_waitlist_promoted,
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
