"""
Garcia Folklorico Studio -- Google Sheets CRM Sync
Mirrors SQLite registrations, waitlist, and rentals to a Google Sheet.

One-way sync: DB is source of truth, Sheet is read-only dashboard for Itzel.
Runs every 15-30 min via cron on VPS.

Usage:
    python -m sheets_sync.run_sync

Prerequisites:
    - Google Cloud service account with Sheets API enabled
    - Service account JSON key file path in .env as GOOGLE_SHEETS_CREDS
    - Google Sheet ID in .env as GOOGLE_SHEET_ID
    - Sheet shared with the service account email
"""

import json
import logging
import sys
from datetime import datetime
from pathlib import Path

# Setup paths
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from auto_config import get_db, GOOGLE_SHEETS_CREDS, GOOGLE_SHEET_ID, AUTOMATION_DIR

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "backend"))
from models import Registration, RentalBooking, Block, ClassType, ClassSlot

from shared_utils import report_status, publish_event

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [sheets_sync] %(message)s",
    handlers=[
        logging.FileHandler(Path(__file__).parent / "sheets_sync.log"),
        logging.StreamHandler(),
    ]
)
log = logging.getLogger(__name__)

STATE_FILE = Path(__file__).parent / "sync_state.json"


def load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {"last_reg_id": 0, "last_rental_id": 0, "last_sync": None}


def save_state(state: dict):
    tmp = str(STATE_FILE) + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=2, default=str)
    Path(tmp).replace(STATE_FILE)


def get_sheet_client():
    """Initialize gspread client with service account credentials."""
    if not GOOGLE_SHEETS_CREDS or not GOOGLE_SHEET_ID:
        log.warning("Google Sheets credentials not configured. Set GOOGLE_SHEETS_CREDS and GOOGLE_SHEET_ID in .env")
        return None, None

    try:
        import gspread
        gc = gspread.service_account(filename=GOOGLE_SHEETS_CREDS)
        spreadsheet = gc.open_by_key(GOOGLE_SHEET_ID)
        return gc, spreadsheet
    except ImportError:
        log.error("gspread not installed. Run: pip install gspread")
        return None, None
    except Exception as e:
        log.error(f"Failed to connect to Google Sheets: {e}")
        return None, None


def sync_registrations(spreadsheet, db):
    """Sync all registrations to the 'Registrations' sheet."""
    try:
        ws = spreadsheet.worksheet("Registrations")
    except Exception:
        ws = spreadsheet.add_worksheet("Registrations", rows=500, cols=12)

    regs = (
        db.query(Registration, ClassType, Block)
        .join(ClassType, Registration.class_type_id == ClassType.id)
        .join(Block, Registration.block_id == Block.id)
        .filter(Registration.status == "registered")
        .order_by(Registration.created_at.desc())
        .all()
    )

    headers = [
        "ID", "Child Name", "Parent Name", "Class (EN)", "Class (ES)",
        "Age", "Phone", "Email", "Session", "Status", "Language", "Registered On"
    ]

    rows = [headers]
    for reg, ct, block in regs:
        rows.append([
            reg.id,
            reg.child_name,
            reg.parent_name,
            ct.name_en,
            ct.name_es,
            reg.child_age,
            reg.phone,
            reg.email,
            block.name,
            reg.status,
            reg.language,
            reg.created_at.strftime("%Y-%m-%d %H:%M") if reg.created_at else "",
        ])

    ws.clear()
    if rows:
        ws.update(rows, value_input_option="RAW")

    log.info(f"Synced {len(rows) - 1} registrations")
    return len(rows) - 1


def sync_waitlist(spreadsheet, db):
    """Sync waitlisted students to the 'Waitlist' sheet."""
    try:
        ws = spreadsheet.worksheet("Waitlist")
    except Exception:
        ws = spreadsheet.add_worksheet("Waitlist", rows=200, cols=12)

    regs = (
        db.query(Registration, ClassType, Block)
        .join(ClassType, Registration.class_type_id == ClassType.id)
        .join(Block, Registration.block_id == Block.id)
        .filter(Registration.status == "waitlisted")
        .order_by(Registration.created_at.asc())
        .all()
    )

    headers = [
        "ID", "Child Name", "Parent Name", "Class (EN)", "Class (ES)",
        "Age", "Phone", "Email", "Session", "Waitlisted Since", "Language"
    ]

    rows = [headers]
    for reg, ct, block in regs:
        rows.append([
            reg.id,
            reg.child_name,
            reg.parent_name,
            ct.name_en,
            ct.name_es,
            reg.child_age,
            reg.phone,
            reg.email,
            block.name,
            reg.created_at.strftime("%Y-%m-%d %H:%M") if reg.created_at else "",
            reg.language,
        ])

    ws.clear()
    if rows:
        ws.update(rows, value_input_option="RAW")

    log.info(f"Synced {len(rows) - 1} waitlisted students")
    return len(rows) - 1


def sync_rentals(spreadsheet, db):
    """Sync rental bookings to the 'Rentals' sheet."""
    try:
        ws = spreadsheet.worksheet("Rentals")
    except Exception:
        ws = spreadsheet.add_worksheet("Rentals", rows=200, cols=12)

    bookings = (
        db.query(RentalBooking)
        .filter(RentalBooking.status == "confirmed")
        .order_by(RentalBooking.date.desc())
        .all()
    )

    headers = [
        "ID", "Date", "Time", "Hours", "Renter", "Phone",
        "Email", "Purpose", "Total", "Status", "Booked On"
    ]

    rows = [headers]
    for b in bookings:
        start = b.start_time.strftime("%I:%M %p").lstrip("0")
        end = b.end_time.strftime("%I:%M %p").lstrip("0")
        rows.append([
            b.id,
            b.date.strftime("%Y-%m-%d"),
            f"{start} - {end}",
            b.hours,
            b.renter_name,
            b.phone,
            b.email,
            b.purpose,
            f"${b.total_price:.0f}",
            b.status,
            b.created_at.strftime("%Y-%m-%d %H:%M") if b.created_at else "",
        ])

    ws.clear()
    if rows:
        ws.update(rows, value_input_option="RAW")

    log.info(f"Synced {len(rows) - 1} rental bookings")
    return len(rows) - 1


def main():
    log.info("Starting Google Sheets CRM sync...")

    gc, spreadsheet = get_sheet_client()
    if not spreadsheet:
        report_status("sheets_sync", "error", "Google Sheets not configured")
        return

    db = get_db()
    try:
        reg_count = sync_registrations(spreadsheet, db)
        wl_count = sync_waitlist(spreadsheet, db)
        rental_count = sync_rentals(spreadsheet, db)

        metrics = {
            "registrations": reg_count,
            "waitlisted": wl_count,
            "rentals": rental_count,
        }

        report_status("sheets_sync", "ok",
                       f"{reg_count} regs, {wl_count} waitlisted, {rental_count} rentals",
                       metrics=metrics)

        publish_event("sheets_sync", "synced", metrics)

        state = load_state()
        state["last_sync"] = datetime.now().isoformat()
        save_state(state)

        log.info(f"Sync complete: {reg_count} regs, {wl_count} waitlisted, {rental_count} rentals")

    except Exception as e:
        log.error(f"Sync failed: {e}", exc_info=True)
        report_status("sheets_sync", "error", str(e))
    finally:
        db.close()


if __name__ == "__main__":
    main()
