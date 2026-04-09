"""
Garcia Folklorico Studio -- Class Reminder Emails
Sends bilingual reminder emails 24 hours before each class session.

Runs daily at 4 PM via cron. Queries tomorrow's classes from the active
block and sends a reminder to each registered parent.

Usage:
    python -m reminders.run_reminders
    python -m reminders.run_reminders --dry-run
"""

import logging
import sys
from datetime import datetime, date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from auto_config import get_db, send_email_sync, STUDIO_EMAIL

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "backend"))
from models import Registration, ClassSlot, ClassType, Block
from services.email import (
    _email, _heading, _sub, _section_header, _detail_table, _detail_row,
    _callout, _btn, _make_ics, _divider, STUDIO_FULL
)

from shared_utils import report_status, publish_event

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [reminders] %(message)s",
    handlers=[
        logging.FileHandler(Path(__file__).parent / "reminders.log"),
        logging.StreamHandler(),
    ]
)
log = logging.getLogger(__name__)

DAY_NAMES_EN = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
DAY_NAMES_ES = ["Lunes", "Martes", "Miercoles", "Jueves", "Viernes", "Sabado", "Domingo"]


def get_tomorrow_classes(db):
    """Get all class slots scheduled for tomorrow in the active block."""
    tomorrow = date.today() + timedelta(days=1)
    tomorrow_dow = tomorrow.weekday()  # 0=Monday matches model

    block = db.query(Block).filter_by(status="active").first()
    if not block:
        log.info("No active block found")
        return [], None, None

    # Check if tomorrow falls within the block dates
    if not (block.start_date <= tomorrow <= block.end_date):
        log.info(f"Tomorrow ({tomorrow}) is outside block {block.name} ({block.start_date} - {block.end_date})")
        return [], block, tomorrow

    slots = (
        db.query(ClassSlot)
        .filter(ClassSlot.block_id == block.id, ClassSlot.day_of_week == tomorrow_dow)
        .all()
    )

    return slots, block, tomorrow


def get_registered_students(db, class_type_id, block_id):
    """Get all registered (not waitlisted/cancelled) students for a class."""
    return (
        db.query(Registration)
        .filter(
            Registration.class_type_id == class_type_id,
            Registration.block_id == block_id,
            Registration.status == "registered"
        )
        .all()
    )


def build_reminder_email(reg, class_type, slot, block, tomorrow):
    """Build bilingual reminder email HTML + subject."""
    is_es = reg.language == "es"
    cls = class_type.name_es if is_es else class_type.name_en
    day_name = DAY_NAMES_ES[tomorrow.weekday()] if is_es else DAY_NAMES_EN[tomorrow.weekday()]
    time_str = slot.start_time.strftime("%I:%M %p").lstrip("0")
    end_str = slot.end_time.strftime("%I:%M %p").lstrip("0")

    if is_es:
        subject = f"Recordatorio: {reg.child_name} tiene {cls} manana - {time_str}"
        preheader = f"Clase de {cls} manana {day_name} a las {time_str}."
    else:
        subject = f"Reminder: {reg.child_name} has {cls} tomorrow - {time_str}"
        preheader = f"{cls} class tomorrow {day_name} at {time_str}."

    # Build content
    if is_es:
        c = _heading(f"Clase Manana!")
        c += _sub(f"<strong>{reg.child_name}</strong> tiene clase de <strong>{cls}</strong> manana.")
    else:
        c = _heading(f"Class Tomorrow!")
        c += _sub(f"<strong>{reg.child_name}</strong> has <strong>{cls}</strong> class tomorrow.")

    c += _section_header("Detalles" if is_es else "Details")
    c += _detail_table(
        _detail_row("Clase" if is_es else "Class", f"<strong>{cls}</strong>"),
        _detail_row("Dia" if is_es else "Day", f"<strong>{day_name}</strong>, {tomorrow.strftime('%B %d')}"),
        _detail_row("Hora" if is_es else "Time", f"{time_str} - {end_str}"),
    )

    c += _divider()

    if is_es:
        c += _callout(
            "Recuerden traer ropa comoda y una botella de agua. "
            "Lleguen 5 minutos antes del inicio de clase."
        )
    else:
        c += _callout(
            "Remember to bring comfortable clothes and a water bottle. "
            "Please arrive 5 minutes before class starts."
        )

    c += _btn(
        "Ver Ubicacion" if is_es else "View Location",
        href="https://maps.google.com/?q=2012+Saviers+Rd+Oxnard+CA+93033"
    )

    html = _email(c, preheader)

    # Build .ics for tomorrow's class
    start_dt = datetime.combine(tomorrow, slot.start_time)
    end_dt = datetime.combine(tomorrow, slot.end_time)
    ics = _make_ics(
        summary=f"{cls} - Garcia Folklorico Studio",
        start=start_dt,
        end=end_dt,
        description=f"{reg.child_name} - {cls}",
        location=STUDIO_FULL,
    )

    return subject, html, ics


def main():
    dry_run = "--dry-run" in sys.argv
    if dry_run:
        log.info("DRY RUN mode - no emails will be sent")

    log.info("Starting class reminder check...")
    db = get_db()
    sent = 0
    skipped = 0
    errors = 0

    try:
        slots, block, tomorrow = get_tomorrow_classes(db)

        if not slots:
            log.info("No classes scheduled for tomorrow")
            report_status("reminders", "ok", "No classes tomorrow", metrics={"sent": 0})
            return

        log.info(f"Found {len(slots)} class slot(s) for tomorrow ({tomorrow})")

        # Group slots by class_type to avoid duplicate emails
        # (a student registered for a class_type gets one reminder even if there are multiple slots)
        seen_parents = set()

        for slot in slots:
            class_type = slot.class_type
            students = get_registered_students(db, class_type.id, block.id)
            log.info(f"  {class_type.name_en}: {len(students)} registered students")

            for reg in students:
                # Deduplicate: same parent + same class = one email
                key = (reg.email, class_type.id)
                if key in seen_parents:
                    skipped += 1
                    continue
                seen_parents.add(key)

                subject, html, ics = build_reminder_email(reg, class_type, slot, block, tomorrow)

                if dry_run:
                    log.info(f"  [DRY RUN] Would send to {reg.email}: {subject}")
                    sent += 1
                    continue

                success = send_email_sync(reg.email, subject, html, ics_data=ics)
                if success:
                    sent += 1
                    log.info(f"  Sent reminder to {reg.email} for {reg.child_name}")
                else:
                    errors += 1
                    log.error(f"  Failed to send to {reg.email}")

        status = "ok" if errors == 0 else "warning"
        detail = f"Sent {sent} reminders, {skipped} skipped, {errors} errors"
        report_status("reminders", status, detail,
                       metrics={"sent": sent, "skipped": skipped, "errors": errors})
        publish_event("reminders", "sent", {"count": sent, "date": str(tomorrow)})
        log.info(detail)

    except Exception as e:
        log.error(f"Reminder run failed: {e}", exc_info=True)
        report_status("reminders", "error", str(e))
    finally:
        db.close()


if __name__ == "__main__":
    main()
