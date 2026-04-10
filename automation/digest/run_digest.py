"""
Garcia Folklorico Studio -- Daily Digest
Sends a morning summary email to the studio owner.

Runs daily at 7 AM via cron.

Usage:
    python -m digest.run_digest
"""

import logging
import sys
from datetime import datetime, timedelta, date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from auto_config import get_db, send_email_sync, STUDIO_EMAIL, ALERT_EMAIL

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "backend"))
from models import Registration, RentalBooking, Block, ClassType

from shared_utils import report_status

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [digest] %(message)s",
    handlers=[
        logging.FileHandler(Path(__file__).parent / "digest.log"),
        logging.StreamHandler(),
    ]
)
log = logging.getLogger(__name__)

ORANGE = "#E8620A"
ORANGE_DARK = "#C4510A"
BG = "#F9F6F2"
TEXT = "#2C2C2C"
MUTED = "#666666"
WHITE = "#FFFFFF"
WARN_BG = "#FFF5E6"
WARN_BORDER = "#E8620A"
GREEN = "#2E7D32"
GREEN_BG = "#E8F5E9"


# ── HTML Helpers ──────────────────────────────────────────────────────

def _wrap(content: str, today_str: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Resumen Diario / Daily Digest</title>
</head>
<body style="margin:0;padding:0;background:{BG};font-family:Arial,Helvetica,sans-serif;color:{TEXT};">
<table width="100%" cellpadding="0" cellspacing="0" border="0" style="background:{BG};">
<tr><td align="center" style="padding:24px 16px;">
<table width="600" cellpadding="0" cellspacing="0" border="0"
       style="max-width:600px;width:100%;background:{WHITE};border-radius:8px;overflow:hidden;
              box-shadow:0 2px 8px rgba(0,0,0,0.08);">

  <!-- Header -->
  <tr>
    <td style="background:{ORANGE};padding:28px 32px;">
      <p style="margin:0;font-size:22px;font-weight:bold;color:{WHITE};letter-spacing:0.3px;">
        Garcia Folklorico Studio
      </p>
      <p style="margin:6px 0 0;font-size:14px;color:rgba(255,255,255,0.88);">
        Resumen Diario &bull; Daily Digest
      </p>
      <p style="margin:8px 0 0;font-size:13px;color:rgba(255,255,255,0.75);">
        {today_str}
      </p>
    </td>
  </tr>

  <!-- Body -->
  <tr><td style="padding:28px 32px 8px;">{content}</td></tr>

  <!-- Footer -->
  <tr>
    <td style="padding:20px 32px 28px;border-top:1px solid #EEEEEE;">
      <p style="margin:0;font-size:12px;color:{MUTED};text-align:center;">
        Garcia Folklorico Studio &bull; 2012 Saviers Rd., Oxnard, CA 93033<br>
        Este correo es solo para uso interno del estudio. / This email is for internal studio use only.
      </p>
    </td>
  </tr>

</table>
</td></tr>
</table>
</body>
</html>"""


def _section(title_es: str, title_en: str) -> str:
    return f"""
<table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-bottom:4px;">
<tr>
  <td style="padding:16px 0 6px;border-bottom:2px solid {ORANGE};">
    <p style="margin:0;font-size:16px;font-weight:bold;color:{ORANGE_DARK};">{title_es}</p>
    <p style="margin:2px 0 0;font-size:12px;color:{MUTED};">{title_en}</p>
  </td>
</tr>
</table>"""


def _stat_row(label_es: str, label_en: str, value: str, highlight: bool = False) -> str:
    val_color = WARN_BORDER if highlight else TEXT
    return f"""<tr>
  <td style="padding:8px 0;border-bottom:1px solid #EEEEEE;font-size:13px;color:{TEXT};">
    {label_es}<br><span style="font-size:11px;color:{MUTED};">{label_en}</span>
  </td>
  <td style="padding:8px 0;border-bottom:1px solid #EEEEEE;font-size:14px;font-weight:bold;
             color:{val_color};text-align:right;">{value}</td>
</tr>"""


def _table_open() -> str:
    return '<table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-bottom:16px;">'


def _table_close() -> str:
    return "</table>"


def _alert_box(text_es: str, text_en: str) -> str:
    return f"""
<table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-bottom:16px;">
<tr>
  <td style="background:{WARN_BG};border-left:4px solid {WARN_BORDER};
             padding:12px 16px;border-radius:4px;">
    <p style="margin:0;font-size:13px;color:{WARN_BORDER};font-weight:bold;">{text_es}</p>
    <p style="margin:4px 0 0;font-size:12px;color:{MUTED};">{text_en}</p>
  </td>
</tr>
</table>"""


def _no_data(text_es: str, text_en: str) -> str:
    return f"""
<p style="font-size:13px;color:{MUTED};font-style:italic;margin:8px 0 16px;">
  {text_es} / {text_en}
</p>"""


def _reg_card(reg: "Registration", ct: "ClassType") -> str:
    return f"""
<table width="100%" cellpadding="0" cellspacing="0" border="0"
       style="margin-bottom:8px;background:{BG};border-radius:6px;padding:0;">
<tr>
  <td style="padding:10px 14px;">
    <p style="margin:0;font-size:13px;font-weight:bold;color:{TEXT};">
      {reg.child_name}
    </p>
    <p style="margin:2px 0 0;font-size:12px;color:{MUTED};">
      {ct.name_es} / {ct.name_en} &bull; Padre/Father: {reg.parent_name}
    </p>
    <p style="margin:2px 0 0;font-size:12px;color:{MUTED};">
      {reg.email} &bull; Pago/Payment: {reg.payment_status}
    </p>
  </td>
</tr>
</table>"""


def _rental_card(rb: "RentalBooking") -> str:
    time_str = rb.start_time.strftime("%I:%M %p").lstrip("0")
    end_str = rb.end_time.strftime("%I:%M %p").lstrip("0")
    return f"""
<table width="100%" cellpadding="0" cellspacing="0" border="0"
       style="margin-bottom:8px;background:{BG};border-radius:6px;">
<tr>
  <td style="padding:10px 14px;">
    <p style="margin:0;font-size:13px;font-weight:bold;color:{TEXT};">
      {rb.renter_name} &bull; {time_str} - {end_str}
    </p>
    <p style="margin:2px 0 0;font-size:12px;color:{MUTED};">
      {rb.purpose} &bull; ${rb.total_price:.0f} &bull; Pago/Payment: {rb.payment_status}
    </p>
  </td>
</tr>
</table>"""


# ── Data queries ──────────────────────────────────────────────────────

def query_digest_data(db):
    today = date.today()
    yesterday = today - timedelta(days=1)
    cutoff = datetime.combine(yesterday, datetime.min.time())

    # New registrations in last 24h
    new_regs = (
        db.query(Registration)
        .filter(Registration.created_at >= cutoff, Registration.status == "registered")
        .order_by(Registration.created_at.desc())
        .all()
    )

    # Cancellations in last 24h
    cancellations = (
        db.query(Registration)
        .filter(Registration.created_at >= cutoff, Registration.status == "cancelled")
        .all()
    )

    # Active block
    active_block = db.query(Block).filter_by(status="active").first()

    # Class type capacity data
    class_types = db.query(ClassType).all()
    capacity_data = []
    near_full = []
    for ct in class_types:
        if active_block:
            enrolled = (
                db.query(Registration)
                .filter(
                    Registration.class_type_id == ct.id,
                    Registration.block_id == active_block.id,
                    Registration.status == "registered",
                )
                .count()
            )
        else:
            enrolled = 0
        pct = (enrolled / ct.max_capacity * 100) if ct.max_capacity else 0
        capacity_data.append({
            "ct": ct,
            "enrolled": enrolled,
            "capacity": ct.max_capacity,
            "pct": pct,
        })
        if pct >= 80:
            near_full.append({
                "ct": ct,
                "enrolled": enrolled,
                "capacity": ct.max_capacity,
                "pct": pct,
            })

    # Unpaid tuition
    unpaid_count = (
        db.query(Registration)
        .filter(
            Registration.payment_status == "unpaid",
            Registration.status == "registered",
        )
        .count()
    )

    # Today's rental bookings
    todays_rentals = (
        db.query(RentalBooking)
        .filter(RentalBooking.date == today, RentalBooking.status == "confirmed")
        .order_by(RentalBooking.start_time)
        .all()
    )

    # Outstanding revenue: unpaid registrations + unpaid rental bookings
    # We don't have a tuition_price on ClassType, so we sum unpaid rentals only
    # and count unpaid registrations separately (no price field on Registration)
    outstanding_rentals = (
        db.query(RentalBooking)
        .filter(
            RentalBooking.payment_status == "unpaid",
            RentalBooking.status == "confirmed",
        )
        .all()
    )
    outstanding_rental_revenue = sum(r.total_price for r in outstanding_rentals)

    return {
        "new_regs": new_regs,
        "cancellations": cancellations,
        "active_block": active_block,
        "capacity_data": capacity_data,
        "near_full": near_full,
        "unpaid_count": unpaid_count,
        "todays_rentals": todays_rentals,
        "outstanding_rental_revenue": outstanding_rental_revenue,
        "outstanding_rentals_count": len(outstanding_rentals),
        "today": today,
        "db": db,
    }


# ── Email builder ─────────────────────────────────────────────────────

def build_digest_html(data: dict) -> str:
    today = data["today"]
    today_str_es = today.strftime("%A, %d de %B de %Y")
    today_str_en = today.strftime("%A, %B %d, %Y")
    today_display = f"{today_str_es} / {today_str_en}"

    content = ""
    db = data["db"]

    # ── 1. Nuevas inscripciones / New Registrations ──────────────────
    content += _section("Nuevas Inscripciones (24h)", "New Registrations (24h)")
    new_regs = data["new_regs"]
    if new_regs:
        content += f'<p style="font-size:13px;color:{TEXT};margin:10px 0 8px;">'
        content += f'<strong>{len(new_regs)}</strong> nueva(s) inscripcion(es) / new registration(s)'
        content += "</p>"
        for reg in new_regs:
            ct = db.query(ClassType).filter_by(id=reg.class_type_id).first()
            content += _reg_card(reg, ct)
    else:
        content += _no_data("Sin nuevas inscripciones en las ultimas 24 horas",
                            "No new registrations in the last 24 hours")

    # ── 2. Cancelaciones / Cancellations ────────────────────────────
    content += _section("Cancelaciones (24h)", "Cancellations (24h)")
    cancellations = data["cancellations"]
    if cancellations:
        content += _alert_box(
            f"{len(cancellations)} cancelacion(es) en las ultimas 24 horas",
            f"{len(cancellations)} cancellation(s) in the last 24 hours"
        )
        for reg in cancellations:
            ct = db.query(ClassType).filter_by(id=reg.class_type_id).first()
            content += _reg_card(reg, ct)
    else:
        content += _no_data("Sin cancelaciones en las ultimas 24 horas",
                            "No cancellations in the last 24 hours")

    # ── 3. Capacidad de Clases / Class Capacity ──────────────────────
    content += _section("Capacidad de Clases", "Class Capacity")
    active_block = data["active_block"]
    if active_block:
        content += f'<p style="font-size:12px;color:{MUTED};margin:8px 0 6px;">'
        content += f'Bloque activo / Active block: <strong>{active_block.name}</strong> '
        content += f'({active_block.start_date} - {active_block.end_date})</p>'
    content += _table_open()
    for item in data["capacity_data"]:
        ct = item["ct"]
        enrolled = item["enrolled"]
        capacity = item["capacity"]
        pct = item["pct"]
        pct_str = f"{enrolled}/{capacity} ({pct:.0f}%)"
        highlight = pct >= 80
        content += _stat_row(ct.name_es, ct.name_en, pct_str, highlight=highlight)
    content += _table_close()

    # Near-full alerts
    near_full = data["near_full"]
    if near_full:
        for item in near_full:
            ct = item["ct"]
            enrolled = item["enrolled"]
            capacity = item["capacity"]
            pct = item["pct"]
            if pct >= 100:
                content += _alert_box(
                    f"LLENO: {ct.name_es} ({enrolled}/{capacity})",
                    f"FULL: {ct.name_en} ({enrolled}/{capacity})"
                )
            else:
                content += _alert_box(
                    f"Casi lleno: {ct.name_es} al {pct:.0f}% ({enrolled}/{capacity})",
                    f"Near capacity: {ct.name_en} at {pct:.0f}% ({enrolled}/{capacity})"
                )

    # ── 4. Pagos Pendientes / Unpaid Tuition ─────────────────────────
    content += _section("Pagos Pendientes", "Unpaid Tuition")
    unpaid_count = data["unpaid_count"]
    highlight_unpaid = unpaid_count > 0
    content += _table_open()
    content += _stat_row(
        "Inscripciones sin pago",
        "Registrations with unpaid status",
        str(unpaid_count),
        highlight=highlight_unpaid,
    )
    content += _stat_row(
        "Rentas sin pagar",
        "Unpaid rental bookings",
        str(data["outstanding_rentals_count"]),
        highlight=data["outstanding_rentals_count"] > 0,
    )
    content += _stat_row(
        "Ingresos pendientes (rentas)",
        "Outstanding revenue (rentals)",
        f"${data['outstanding_rental_revenue']:.2f}",
        highlight=data["outstanding_rental_revenue"] > 0,
    )
    content += _table_close()

    # ── 5. Rentas de Hoy / Today's Rentals ──────────────────────────
    content += _section("Rentas de Hoy", "Today's Rentals")
    todays_rentals = data["todays_rentals"]
    if todays_rentals:
        content += f'<p style="font-size:13px;color:{TEXT};margin:10px 0 8px;">'
        content += f'<strong>{len(todays_rentals)}</strong> renta(s) hoy / rental(s) today</p>'
        for rb in todays_rentals:
            content += _rental_card(rb)
    else:
        content += _no_data("Sin rentas programadas para hoy",
                            "No rentals scheduled for today")

    return _wrap(content, today_display)


# ── Main ──────────────────────────────────────────────────────────────

def main():
    log.info("Starting daily digest...")
    db = get_db()

    try:
        data = query_digest_data(db)
        html = build_digest_html(data)

        today = data["today"]
        subject = f"Resumen Diario / Daily Digest - {today.strftime('%B %d, %Y')}"

        recipient = STUDIO_EMAIL or ALERT_EMAIL
        if not recipient:
            log.error("No STUDIO_EMAIL or ALERT_EMAIL configured -- digest not sent")
            report_status("digest", "error", "No recipient configured")
            return

        success = send_email_sync(recipient, subject, html)

        if success:
            log.info(f"Digest sent to {recipient}")
            report_status(
                "digest", "ok",
                f"Sent to {recipient}",
                metrics={
                    "new_regs": len(data["new_regs"]),
                    "cancellations": len(data["cancellations"]),
                    "unpaid": data["unpaid_count"],
                    "todays_rentals": len(data["todays_rentals"]),
                },
            )
        else:
            log.error("Failed to send digest email")
            report_status("digest", "error", "Email send failed")

    except Exception as e:
        log.error(f"Digest failed: {e}", exc_info=True)
        report_status("digest", "error", str(e))
    finally:
        db.close()


if __name__ == "__main__":
    main()
