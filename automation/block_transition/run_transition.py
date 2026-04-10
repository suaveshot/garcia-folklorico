"""
Garcia Folklorico Studio -- Block Transition Automation
Handles end-of-block student transitions.

Runs daily at 1 AM via cron.

Usage:
    python -m block_transition.run_transition
"""

import logging
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from auto_config import get_db, send_email_sync, ALERT_EMAIL

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "backend"))
from models import Block, Registration, ClassType

from shared_utils import report_status, publish_event

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [block_transition] %(message)s",
    handlers=[
        logging.FileHandler(Path(__file__).parent / "block_transition.log"),
        logging.StreamHandler(),
    ]
)
log = logging.getLogger(__name__)


def build_summary_html(block_name: str, students_completed: int,
                       next_block_name: str | None) -> str:
    next_block_line = (
        f"<p>Proximo bloque activado / Next block activated: <strong>{next_block_name}</strong></p>"
        if next_block_name
        else "<p>No hay proximo bloque configurado / No upcoming block configured.</p>"
    )
    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family:Arial,sans-serif;color:#2C2C2C;padding:24px;">
  <h2 style="color:#E8620A;">Fin de Bloque / Block Ended</h2>
  <p>El bloque <strong>{block_name}</strong> ha terminado.</p>
  <p>Estudiantes completados / Students completed: <strong>{students_completed}</strong></p>
  {next_block_line}
  <p style="color:#666;font-size:12px;margin-top:24px;">
    Garcia Folklorico Studio &bull; Automation Report
  </p>
</body>
</html>"""


def main():
    log.info("Starting block transition check...")
    db = get_db()
    today = date.today()

    try:
        active_block = db.query(Block).filter_by(status="active").first()

        if not active_block:
            log.info("No active block found -- nothing to do")
            report_status("block_transition", "ok", "No active block")
            return

        if active_block.end_date >= today:
            log.info(
                f"Active block '{active_block.name}' ends {active_block.end_date} -- "
                "not yet ended, nothing to do"
            )
            report_status("block_transition", "ok",
                          f"Block '{active_block.name}' still active until {active_block.end_date}")
            return

        # Block has ended
        log.info(f"Block '{active_block.name}' has ended (end_date={active_block.end_date})")

        # Count registered students in the ended block
        registered_regs = (
            db.query(Registration)
            .filter(
                Registration.block_id == active_block.id,
                Registration.status == "registered",
            )
            .all()
        )
        students_completed = len(registered_regs)
        log.info(f"  {students_completed} registered student(s) completed this block")

        # Mark block as past
        active_block.status = "past"
        db.commit()
        log.info(f"  Block '{active_block.name}' status set to 'past'")

        # Publish block-ended event
        publish_event("block_transition", "block_ended", {
            "block_name": active_block.name,
            "students_completed": students_completed,
        })

        # Publish per-student completion events (for CRM Alumni marking)
        for reg in registered_regs:
            ct = db.query(ClassType).filter_by(id=reg.class_type_id).first()
            class_name = ct.name_en if ct else "Unknown"
            publish_event("registration", "block_completed", {
                "registration_id": reg.id,
                "child_name": reg.child_name,
                "parent_name": reg.parent_name,
                "class_name": class_name,
                "block_name": active_block.name,
            })
            log.info(f"    -> block_completed event for {reg.child_name} ({class_name})")

        # Activate next upcoming block (if any)
        next_block = (
            db.query(Block)
            .filter_by(status="upcoming")
            .order_by(Block.start_date)
            .first()
        )
        next_block_name = None
        if next_block:
            next_block.status = "active"
            db.commit()
            next_block_name = next_block.name
            log.info(f"  Next block '{next_block.name}' activated")
        else:
            log.info("  No upcoming block found -- studio is between sessions")

        # Send summary to ALERT_EMAIL
        if ALERT_EMAIL:
            subject = f"Garcia Studio: Block '{active_block.name}' Ended -- {students_completed} Students"
            html = build_summary_html(active_block.name, students_completed, next_block_name)
            ok = send_email_sync(ALERT_EMAIL, subject, html)
            if ok:
                log.info(f"  Summary email sent to {ALERT_EMAIL}")
            else:
                log.warning(f"  Failed to send summary email to {ALERT_EMAIL}")
        else:
            log.warning("  No ALERT_EMAIL configured -- skipping summary email")

        report_status(
            "block_transition", "ok",
            f"Block '{active_block.name}' transitioned: {students_completed} alumni",
            metrics={
                "block": active_block.name,
                "students_completed": students_completed,
                "next_block": next_block_name or "none",
            },
        )
        log.info("Block transition complete")

    except Exception as e:
        log.error(f"Block transition failed: {e}", exc_info=True)
        report_status("block_transition", "error", str(e))
    finally:
        db.close()


if __name__ == "__main__":
    main()
