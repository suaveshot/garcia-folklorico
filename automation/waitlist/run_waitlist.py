"""
Garcia Folklorico Studio -- Waitlist Follow-Up Engine
Manages the 48-hour waitlist claim window with automated reminders.

Flow:
1. Backend sends initial "spot opened" email when a registered student cancels
2. This engine detects waitlisted students with open spots (promoted but unconfirmed)
3. At 24 hours: sends a reminder email
4. At 48 hours: auto-cancels the waitlisted student, promotes next in line

Runs every 2 hours via cron on VPS.

Usage:
    python -m waitlist.run_waitlist
    python -m waitlist.run_waitlist --dry-run
"""

import json
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from auto_config import get_db, send_email_sync, STUDIO_EMAIL, ALERT_EMAIL

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "backend"))
from models import Registration, ClassType, Block
from services.email import (
    _email, _heading, _sub, _callout, _btn, _section_header,
    _detail_table, _detail_row, _divider
)
from routes.schedule import get_registered_count

from shared_utils import report_status, publish_event

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [waitlist] %(message)s",
    handlers=[
        logging.FileHandler(Path(__file__).parent / "waitlist.log"),
        logging.StreamHandler(),
    ]
)
log = logging.getLogger(__name__)

STATE_FILE = Path(__file__).parent / "waitlist_state.json"

REMINDER_HOURS = 24
EXPIRY_HOURS = 48


def load_state() -> dict:
    """Load waitlist tracking state. Keys are registration IDs (as strings)."""
    try:
        return json.loads(STATE_FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_state(state: dict):
    tmp = str(STATE_FILE) + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=2, default=str)
    Path(tmp).replace(STATE_FILE)


def find_promoted_waitlisters(db):
    """
    Find waitlisted students where the class now has open spots.
    These are effectively 'promoted but unconfirmed'.
    """
    block = db.query(Block).filter_by(status="active").first()
    if not block:
        return [], None

    waitlisted = (
        db.query(Registration)
        .filter(
            Registration.block_id == block.id,
            Registration.status == "waitlisted"
        )
        .order_by(Registration.class_type_id, Registration.created_at)
        .all()
    )

    promoted = []
    seen_class_types = {}

    for reg in waitlisted:
        ct_id = reg.class_type_id

        if ct_id not in seen_class_types:
            ct = db.query(ClassType).filter_by(id=ct_id).first()
            count = get_registered_count(db, ct_id, block.id)
            seen_class_types[ct_id] = {
                "class_type": ct,
                "registered": count,
                "capacity": ct.max_capacity,
                "spots_open": ct.max_capacity - count,
            }

        info = seen_class_types[ct_id]
        if info["spots_open"] > 0:
            # This student is next in line and there's a spot
            promoted.append((reg, info["class_type"]))
            info["spots_open"] -= 1  # Reserve this spot conceptually

    return promoted, block


def build_reminder_email(reg, class_type):
    """Build 24-hour reminder email for unconfirmed waitlist promotion."""
    is_es = reg.language == "es"
    cls = class_type.name_es if is_es else class_type.name_en

    if is_es:
        subject = f"Recordatorio: Confirme el lugar de {reg.child_name} en {cls}"
        preheader = f"Solo quedan 24 horas para confirmar el lugar de {reg.child_name}."
    else:
        subject = f"Reminder: Confirm {reg.child_name}'s spot in {cls}"
        preheader = f"Only 24 hours left to confirm {reg.child_name}'s spot."

    if is_es:
        c = _heading("Ultimo Recordatorio")
        c += _sub(
            f"Se abrio un espacio en <strong>{cls}</strong> para "
            f"<strong>{reg.child_name}</strong>, pero aun no se ha confirmado."
        )
        c += _callout(
            "Le quedan <strong>24 horas</strong> para confirmar. "
            "Si no confirma, el lugar se ofrecera al siguiente en la lista.",
            "#E8620A", "#FFF5E6"
        )
    else:
        c = _heading("Final Reminder")
        c += _sub(
            f"A spot opened in <strong>{cls}</strong> for "
            f"<strong>{reg.child_name}</strong>, but it hasn't been confirmed yet."
        )
        c += _callout(
            "You have <strong>24 hours left</strong> to confirm. "
            "If not confirmed, the spot will go to the next person on the waitlist.",
            "#E8620A", "#FFF5E6"
        )

    c += _btn("Confirmar Ahora" if is_es else "Confirm Now")

    return subject, _email(c, preheader)


def build_expiry_email(reg, class_type):
    """Build notification that the waitlist claim window has expired."""
    is_es = reg.language == "es"
    cls = class_type.name_es if is_es else class_type.name_en

    if is_es:
        subject = f"Aviso: El espacio de {reg.child_name} en {cls} ha expirado"
        preheader = f"El periodo de confirmacion de 48 horas ha pasado."
    else:
        subject = f"Notice: {reg.child_name}'s spot in {cls} has expired"
        preheader = f"The 48-hour confirmation window has passed."

    if is_es:
        c = _heading("Espacio Expirado")
        c += _sub(
            f"El periodo de confirmacion de 48 horas para el espacio de "
            f"<strong>{reg.child_name}</strong> en <strong>{cls}</strong> ha pasado."
        )
        c += _callout(
            "Si todavia esta interesado/a, contactenos y lo agregaremos de nuevo a la lista de espera.",
            "#C9A0DC", "#f8f0ff"
        )
    else:
        c = _heading("Spot Expired")
        c += _sub(
            f"The 48-hour confirmation window for "
            f"<strong>{reg.child_name}</strong>'s spot in <strong>{cls}</strong> has passed."
        )
        c += _callout(
            "If you're still interested, contact us and we'll add you back to the waitlist.",
            "#C9A0DC", "#f8f0ff"
        )

    c += _btn("Contactenos" if is_es else "Contact Us")

    return subject, _email(c, preheader)


def main():
    dry_run = "--dry-run" in sys.argv
    if dry_run:
        log.info("DRY RUN mode")

    log.info("Starting waitlist follow-up check...")
    db = get_db()
    state = load_state()
    now = datetime.now()

    reminders_sent = 0
    expired = 0
    new_tracked = 0
    errors = 0

    try:
        promoted, block = find_promoted_waitlisters(db)

        if not block:
            log.info("No active block")
            report_status("waitlist", "ok", "No active block")
            return

        if not promoted:
            log.info("No waitlisted students with open spots")
            # Clean up state entries for students no longer waitlisted
            state = {k: v for k, v in state.items()
                     if db.query(Registration).filter_by(
                         id=int(k), status="waitlisted").first() is not None}
            save_state(state)
            report_status("waitlist", "ok", "No promoted waitlisters")
            return

        for reg, class_type in promoted:
            reg_key = str(reg.id)

            # First time seeing this promotion
            if reg_key not in state:
                state[reg_key] = {
                    "detected_at": now.isoformat(),
                    "reminder_sent": False,
                    "child_name": reg.child_name,
                    "class_name": class_type.name_en,
                }
                new_tracked += 1
                log.info(f"  New promotion detected: {reg.child_name} in {class_type.name_en}")
                continue

            entry = state[reg_key]
            detected_at = datetime.fromisoformat(entry["detected_at"])
            hours_elapsed = (now - detected_at).total_seconds() / 3600

            # 48+ hours: auto-expire
            if hours_elapsed >= EXPIRY_HOURS:
                log.info(f"  Expiring: {reg.child_name} ({hours_elapsed:.1f}h since detection)")

                if not dry_run:
                    # Cancel the waitlisted registration
                    reg.status = "cancelled"
                    db.commit()

                    # Send expiry notification
                    subject, html = build_expiry_email(reg, class_type)
                    send_email_sync(reg.email, subject, html)

                    # Notify studio
                    if STUDIO_EMAIL:
                        send_email_sync(
                            STUDIO_EMAIL,
                            f"Waitlist Expired: {reg.child_name} - {class_type.name_en}",
                            _email(
                                _heading("Waitlist Claim Expired")
                                + _sub(f"<strong>{reg.child_name}</strong> did not confirm within 48 hours. "
                                       f"Registration cancelled. Next waitlisted student (if any) will be notified.")
                            )
                        )

                # Remove from state
                del state[reg_key]
                expired += 1

            # 24+ hours: send reminder (once)
            elif hours_elapsed >= REMINDER_HOURS and not entry.get("reminder_sent"):
                log.info(f"  Sending 24hr reminder: {reg.child_name} ({hours_elapsed:.1f}h)")

                if not dry_run:
                    subject, html = build_reminder_email(reg, class_type)
                    success = send_email_sync(reg.email, subject, html)
                    if success:
                        state[reg_key]["reminder_sent"] = True
                        reminders_sent += 1
                    else:
                        errors += 1
                else:
                    reminders_sent += 1

            else:
                log.info(f"  Tracking: {reg.child_name} ({hours_elapsed:.1f}h, reminder={'sent' if entry.get('reminder_sent') else 'pending'})")

        save_state(state)

        status = "ok" if errors == 0 else "warning"
        detail = f"{new_tracked} new, {reminders_sent} reminders, {expired} expired, {errors} errors"
        report_status("waitlist", status, detail,
                       metrics={"new": new_tracked, "reminders": reminders_sent,
                                "expired": expired, "errors": errors})

        if expired > 0:
            publish_event("waitlist", "expired", {"count": expired})

        log.info(detail)

    except Exception as e:
        log.error(f"Waitlist check failed: {e}", exc_info=True)
        report_status("waitlist", "error", str(e))
    finally:
        db.close()


if __name__ == "__main__":
    main()
