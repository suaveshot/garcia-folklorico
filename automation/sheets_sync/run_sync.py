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
    """Sync active registrations to the 'Active Students' tab.

    Writes data rows starting at row 2, preserving the formatted header
    row created by create_crm.py.
    """
    try:
        ws = spreadsheet.worksheet("Active Students")
    except Exception:
        ws = spreadsheet.add_worksheet("Active Students", rows=500, cols=13)

    regs = (
        db.query(Registration, ClassType, Block)
        .join(ClassType, Registration.class_type_id == ClassType.id)
        .join(Block, Registration.block_id == Block.id)
        .filter(Registration.status == "registered")
        .order_by(Registration.created_at.desc())
        .all()
    )

    # Column order matches create_crm.py Active Students tab (A-L, skip M formula col)
    rows = []
    for reg, ct, block in regs:
        rows.append([
            reg.id,
            reg.child_name,
            ct.name_en,
            reg.child_age,
            block.name,
            reg.parent_name,
            reg.phone,
            reg.email,
            reg.emergency_contact,
            reg.language.upper() if reg.language else "EN",
            reg.created_at.strftime("%Y-%m-%d %H:%M") if reg.created_at else "",
            "Active",
        ])

    # Clear data rows only (preserve header formatting in row 1)
    ws.batch_clear(["A2:L500"])
    if rows:
        ws.update(f"A2:L{1 + len(rows)}", rows, value_input_option="RAW")

    log.info(f"Synced {len(rows)} active students")
    return len(rows)


def sync_waitlist(spreadsheet, db):
    """Sync waitlisted students to the 'Waitlist' tab.

    Writes cols A-I (identity + waitlisted-since). Cols J-M (claim status,
    spot offered, deadline, hours remaining) are managed by Itzel/automation
    and are NOT overwritten.
    """
    try:
        ws = spreadsheet.worksheet("Waitlist")
    except Exception:
        ws = spreadsheet.add_worksheet("Waitlist", rows=200, cols=13)

    regs = (
        db.query(Registration, ClassType, Block)
        .join(ClassType, Registration.class_type_id == ClassType.id)
        .join(Block, Registration.block_id == Block.id)
        .filter(Registration.status == "waitlisted")
        .order_by(Registration.created_at.asc())
        .all()
    )

    # Column order matches create_crm.py Waitlist tab (A-I only)
    rows = []
    for reg, ct, block in regs:
        rows.append([
            reg.id,
            reg.child_name,
            reg.parent_name,
            ct.name_en,
            reg.child_age,
            reg.phone,
            reg.email,
            reg.language.upper() if reg.language else "EN",
            reg.created_at.strftime("%Y-%m-%d %H:%M") if reg.created_at else "",
        ])

    # Clear only synced columns (A-I), preserve claim tracking cols (J-M)
    ws.batch_clear(["A2:I200"])
    if rows:
        ws.update(f"A2:I{1 + len(rows)}", rows, value_input_option="RAW")

    log.info(f"Synced {len(rows)} waitlisted students")
    return len(rows)


def sync_rentals(spreadsheet, db):
    """Sync rental bookings to the 'Rental Bookings' tab.

    Writes cols A-I (identity + booking details). Cols J-K (rate/total)
    are formula-driven in the sheet and are NOT overwritten. Cols L-N
    (status, language, booked-on) are written.
    """
    try:
        ws = spreadsheet.worksheet("Rental Bookings")
    except Exception:
        ws = spreadsheet.add_worksheet("Rental Bookings", rows=300, cols=14)

    bookings = (
        db.query(RentalBooking)
        .order_by(RentalBooking.date.desc())
        .all()
    )

    # Column order matches create_crm.py Rental Bookings tab
    # A-E: ID, Date, Start, End, Hours | F-I: Renter, Phone, Email, Purpose
    # J-K: Rate/Total (formulas - skip) | L-N: Status, Language, Booked On
    rows_left = []   # A-I
    rows_right = []  # L-N
    for b in bookings:
        start = b.start_time.strftime("%I:%M %p").lstrip("0") if b.start_time else ""
        end = b.end_time.strftime("%I:%M %p").lstrip("0") if b.end_time else ""
        rows_left.append([
            b.id,
            b.date.strftime("%Y-%m-%d") if b.date else "",
            start,
            end,
            b.hours,
            b.renter_name,
            b.phone,
            b.email,
            b.purpose,
        ])
        rows_right.append([
            b.status,
            b.language.upper() if b.language else "EN",
            b.created_at.strftime("%Y-%m-%d %H:%M") if b.created_at else "",
        ])

    # Clear data rows (preserve header + rate/total formulas in J-K)
    ws.batch_clear(["A2:I300", "L2:N300"])
    if rows_left:
        ws.update(f"A2:I{1 + len(rows_left)}", rows_left, value_input_option="RAW")
        ws.update(f"L2:N{1 + len(rows_right)}", rows_right, value_input_option="RAW")

    log.info(f"Synced {len(rows_left)} rental bookings")
    return len(rows_left)


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
