"""
Garcia Folklorico Studio -- Monthly Report
Sends a bilingual enrollment + revenue summary to Itzel and Sam.

Runs on the 1st of each month at 9 AM via cron.

Usage:
    python -m monthly_report.run_monthly_report
    python -m monthly_report.run_monthly_report --month 2026-07
    python -m monthly_report.run_monthly_report --dry-run
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime, date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from auto_config import get_db, send_email_sync, STUDIO_EMAIL, ALERT_EMAIL

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "backend"))
from models import Registration, RentalBooking, Block, ClassType, ClassSlot
from services.email import (
    _email, _heading, _sub, _section_header, _detail_table, _detail_row,
    _callout, _divider, _price,
)

from shared_utils import report_status, publish_event

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [monthly_report] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(Path(__file__).parent / "monthly_report.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("monthly_report")

STATE_FILE = Path(__file__).parent / "report_state.json"

MONTH_NAMES_EN = [
    "", "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]
MONTH_NAMES_ES = [
    "", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
]


def _load_state() -> dict:
    if STATE_FILE.exists():
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"last_report_month": "", "reports_sent": 0}


def _save_state(state: dict):
    tmp = str(STATE_FILE) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
    os.replace(tmp, str(STATE_FILE))


def collect_metrics(db, year: int, month: int) -> dict:
    """Query SQLite for all enrollment and rental data in the given month."""
    from sqlalchemy import extract, func

    month_start = date(year, month, 1)
    if month == 12:
        month_end = date(year + 1, 1, 1)
    else:
        month_end = date(year, month + 1, 1)

    # Active block(s) during this month
    blocks = db.query(Block).filter(
        Block.start_date < month_end,
        Block.end_date >= month_start,
    ).all()

    block_ids = [b.id for b in blocks]

    # All class types
    class_types = db.query(ClassType).all()
    ct_map = {ct.id: ct for ct in class_types}

    # Registrations created this month
    new_regs = db.query(Registration).filter(
        Registration.created_at >= datetime(year, month, 1),
        Registration.created_at < datetime(*month_end.timetuple()[:3]),
    ).all()

    # Total enrolled per class (in active blocks)
    enrollment = {}
    waitlist = {}
    for ct in class_types:
        for block in blocks:
            enrolled = db.query(Registration).filter(
                Registration.class_type_id == ct.id,
                Registration.block_id == block.id,
                Registration.status == "registered",
            ).count()
            waitlisted = db.query(Registration).filter(
                Registration.class_type_id == ct.id,
                Registration.block_id == block.id,
                Registration.status == "waitlisted",
            ).count()
            key = (ct.id, block.id)
            enrollment[key] = enrolled
            waitlist[key] = waitlisted

    # Cancellations this month
    cancellations = [r for r in new_regs if r.status == "cancelled"]

    # Rentals this month
    rentals = db.query(RentalBooking).filter(
        RentalBooking.date >= month_start,
        RentalBooking.date < month_end,
        RentalBooking.status == "confirmed",
    ).all()

    rental_revenue = sum(r.total_price for r in rentals)
    rental_hours = sum(r.hours for r in rentals)

    # Build per-class summary
    class_summaries = []
    for ct in class_types:
        total_enrolled = 0
        total_waitlisted = 0
        for block in blocks:
            key = (ct.id, block.id)
            total_enrolled += enrollment.get(key, 0)
            total_waitlisted += waitlist.get(key, 0)
        new_this_month = len([
            r for r in new_regs
            if r.class_type_id == ct.id and r.status in ("registered", "waitlisted")
        ])
        pct = round(total_enrolled / ct.max_capacity * 100) if ct.max_capacity else 0
        class_summaries.append({
            "name_en": ct.name_en,
            "name_es": ct.name_es,
            "age_range_en": ct.age_range_text_en,
            "age_range_es": ct.age_range_text_es,
            "max_capacity": ct.max_capacity,
            "enrolled": total_enrolled,
            "waitlisted": total_waitlisted,
            "new_this_month": new_this_month,
            "utilization_pct": pct,
        })

    return {
        "blocks": [{"name": b.name, "status": b.status} for b in blocks],
        "classes": class_summaries,
        "new_registrations": len([r for r in new_regs if r.status != "cancelled"]),
        "cancellations": len(cancellations),
        "rentals_count": len(rentals),
        "rental_hours": rental_hours,
        "rental_revenue": rental_revenue,
    }


def _bar(pct: int) -> str:
    """Inline HTML progress bar for capacity utilization."""
    color = "#2e7d32" if pct < 80 else "#E8620A" if pct < 100 else "#c62828"
    width = min(pct, 100)
    return (
        f'<div style="background:#f0e6d6;border-radius:6px;height:10px;width:120px;display:inline-block;vertical-align:middle;">'
        f'<div style="background:{color};border-radius:6px;height:10px;width:{width}%;"></div></div>'
        f' <span style="font-size:13px;color:#4A154B;font-weight:700;">{pct}%</span>'
    )


def build_email_html(metrics: dict, month_en: str, month_es: str) -> str:
    """Build branded bilingual monthly report email."""
    c = _heading(f"Monthly Report / Reporte Mensual")
    c += _sub(f"{month_en} / {month_es}")

    # Block info
    if metrics["blocks"]:
        block_names = ", ".join(b["name"] for b in metrics["blocks"])
        c += _callout(
            f"<strong>Active Block:</strong> {block_names}<br>"
            f"<strong>Bloque Activo:</strong> {block_names}",
            "#C9A0DC", "#f8f0ff"
        )

    # Summary numbers
    c += _section_header("Overview / Resumen")
    c += _detail_table(
        _detail_row("New Students<br>Nuevos", f"<strong>{metrics['new_registrations']}</strong>"),
        _detail_row("Cancellations<br>Cancelaciones", f"<strong>{metrics['cancellations']}</strong>"),
        _detail_row("Rentals<br>Rentas", f"<strong>{metrics['rentals_count']}</strong> ({metrics['rental_hours']} hrs)"),
    )

    if metrics["rental_revenue"] > 0:
        c += _price(
            f"${metrics['rental_revenue']:.0f}",
            label_en="Rental Revenue / Ingresos por Renta",
        )

    # Per-class breakdown
    c += _section_header("Class Enrollment / Inscripciones por Clase")

    for cls in metrics["classes"]:
        bar = _bar(cls["utilization_pct"])
        wl = f' <span style="color:#E8620A;font-size:12px;">(+{cls["waitlisted"]} waitlist)</span>' if cls["waitlisted"] else ""
        new_badge = f' <span style="color:#2e7d32;font-size:12px;">(+{cls["new_this_month"]} new)</span>' if cls["new_this_month"] else ""

        c += (
            f'<table role="presentation" cellpadding="0" cellspacing="0" width="100%" style="margin:8px 0;">'
            f'<tr><td style="padding:6px 0;">'
            f'<strong class="text-purple" style="color:#4A154B;font-size:15px;">{cls["name_en"]}</strong>'
            f' <span class="text-muted" style="color:#8a7a6a;font-size:12px;">/ {cls["name_es"]}</span>'
            f'<br><span style="font-size:13px;color:#8a7a6a;">{cls["age_range_en"]}</span>'
            f'<br>{cls["enrolled"]} / {cls["max_capacity"]} {bar}{wl}{new_badge}'
            f'</td></tr></table>'
        )

    c += _divider()
    c += _callout(
        "This report is auto-generated on the 1st of each month.<br>"
        "Este reporte se genera automaticamente el 1ro de cada mes.",
    )

    return _email(c, preheader=f"Garcia Folklorico {month_en} Report")


def run(month: str = "", dry_run: bool = False):
    """Generate and send the monthly report."""
    now = datetime.now()
    if month:
        year, mon = map(int, month.split("-"))
    else:
        # Report on the previous month
        prev = now.replace(day=1) - timedelta(days=1)
        year, mon = prev.year, prev.month

    month_key = f"{year}-{mon:02d}"
    month_en = f"{MONTH_NAMES_EN[mon]} {year}"
    month_es = f"{MONTH_NAMES_ES[mon]} {year}"
    log.info("Generating monthly report for %s", month_en)

    # Check if already sent
    state = _load_state()
    if state.get("last_report_month") == month_key and not dry_run:
        log.info("Report for %s already sent. Use --dry-run to preview.", month_en)
        report_status("monthly_report", "ok", f"Already sent for {month_key}")
        return

    # Collect data
    db = get_db()
    try:
        metrics = collect_metrics(db, year, mon)
    finally:
        db.close()

    log.info(
        "Metrics: %d new regs, %d cancellations, %d rentals ($%.0f)",
        metrics["new_registrations"],
        metrics["cancellations"],
        metrics["rentals_count"],
        metrics["rental_revenue"],
    )

    # Generate HTML
    html = build_email_html(metrics, month_en, month_es)

    if dry_run:
        output = Path(__file__).parent / f"preview_{month_key}.html"
        output.write_text(html, encoding="utf-8")
        log.info("Preview saved: %s", output)
        log.info("Metrics: %s", json.dumps(metrics, indent=2, default=str))
        report_status("monthly_report", "ok", f"Dry run for {month_key}")
        return

    # Send to Itzel + Sam
    subject = f"Monthly Report / Reporte Mensual -- {month_en} | Garcia Folklorico Studio"
    recipients = [r for r in [STUDIO_EMAIL, ALERT_EMAIL] if r]

    sent = 0
    for to in recipients:
        if send_email_sync(to, subject, html):
            sent += 1
            log.info("Report sent to %s", to)
        else:
            log.error("Failed to send report to %s", to)

    if sent == 0:
        report_status("monthly_report", "error", "Failed to send to any recipient")
        return

    # Update state
    state["last_report_month"] = month_key
    state["reports_sent"] = state.get("reports_sent", 0) + 1
    _save_state(state)

    # Health + event bus
    report_status("monthly_report", "ok", f"Sent for {month_key}", metrics={
        "new_registrations": metrics["new_registrations"],
        "cancellations": metrics["cancellations"],
        "rentals": metrics["rentals_count"],
        "rental_revenue": metrics["rental_revenue"],
    })
    publish_event("monthly_report", "sent", {
        "month": month_key,
        "new_registrations": metrics["new_registrations"],
        "rental_revenue": metrics["rental_revenue"],
        "recipients": recipients,
    })

    log.info("Monthly report for %s complete. Sent to %d recipient(s).", month_en, sent)


def main():
    parser = argparse.ArgumentParser(description="Garcia Folklorico Monthly Report")
    parser.add_argument("--month", default="", help="Month to report on (YYYY-MM)")
    parser.add_argument("--dry-run", action="store_true", help="Generate preview without sending")
    args = parser.parse_args()

    try:
        run(args.month, args.dry_run)
    except Exception as e:
        log.exception("Monthly report failed: %s", e)
        report_status("monthly_report", "error", str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()
