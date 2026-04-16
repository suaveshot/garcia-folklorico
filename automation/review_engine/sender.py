"""
Garcia Folklorico Studio -- Review Request Email Builder
Builds and sends bilingual review request emails using Garcia's branded template.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from auto_config import send_email_sync

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "backend"))
from services.email import (
    _email, _heading, _sub, _section_header, _callout, _btn, _divider,
)

GOOGLE_REVIEW_URL = os.getenv(
    "GOOGLE_REVIEW_URL",
    "https://g.page/r/CdG8h7neothSEBM/review",
)


def _review_btn(text: str) -> str:
    """Review button linking to Google."""
    return (
        f'<table role="presentation" cellpadding="0" cellspacing="0" align="center" style="margin:16px auto 8px;">'
        f'<tr><td class="btn-bg" align="center" style="padding:13px 36px;background-color:#E8620A;border-radius:50px;">'
        f'<a href="{GOOGLE_REVIEW_URL}" style="font-size:14px;font-weight:700;color:#ffffff;text-decoration:none;display:block;">{text}</a>'
        f'</td></tr></table>'
    )


def build_class_review_email(entry: dict) -> tuple:
    """Build a review request email for a class parent. Returns (subject, html)."""
    is_es = entry.get("language") == "es"
    name = entry["parent_name"].split()[0]  # First name only
    child = entry["child_name"]
    cls = entry["class_name_es"] if is_es else entry["class_name_en"]

    if is_es:
        subject = f"Como fue la experiencia de {child} en {cls}? -- Garcia Folklorico Studio"
        preheader = f"Nos encantaria saber como fue la experiencia de {child}."

        c = _heading(f"Hola {name}!")
        c += _sub(
            f"Esperamos que <strong>{child}</strong> haya disfrutado su tiempo en "
            f"<strong>{cls}</strong>. Su experiencia es muy importante para nosotros "
            f"y para otras familias que buscan clases de folklorico."
        )
        c += _callout(
            "Si tuvo una buena experiencia, nos ayudaria mucho que dejara una "
            "resena en Google. Solo toma un minuto y ayuda a otras familias "
            "a encontrarnos.",
            "#2e7d32", "#f0f8f0",
        )
        c += _review_btn("Dejar una Resena")
        c += _divider()
        c += '<p class="text-muted" style="margin:0;font-size:13px;color:#8a7a6a;text-align:center;line-height:1.5;">Gracias por ser parte de nuestra familia folklorica.</p>'

    else:
        subject = f"How was {child}'s experience in {cls}? -- Garcia Folklorico Studio"
        preheader = f"We'd love to hear how {child}'s experience was."

        c = _heading(f"Hi {name}!")
        c += _sub(
            f"We hope <strong>{child}</strong> enjoyed their time in "
            f"<strong>{cls}</strong>. Your experience means a lot to us "
            f"and to other families looking for folklorico classes."
        )
        c += _callout(
            "If you had a great experience, a Google review would mean the world "
            "to us. It only takes a minute and helps other families find us.",
            "#2e7d32", "#f0f8f0",
        )
        c += _review_btn("Leave a Review")
        c += _divider()
        c += '<p class="text-muted" style="margin:0;font-size:13px;color:#8a7a6a;text-align:center;line-height:1.5;">Thank you for being part of our folklorico family.</p>'

    html = _email(c, preheader=preheader)
    return subject, html


def build_rental_review_email(entry: dict) -> tuple:
    """Build a review request email for a rental client. Returns (subject, html)."""
    is_es = entry.get("language") == "es"
    name = entry["renter_name"].split()[0]

    if is_es:
        subject = "Como fue su renta del estudio? -- Garcia Folklorico Studio"
        preheader = "Nos encantaria saber como fue su experiencia rentando el estudio."

        c = _heading(f"Hola {name}!")
        c += _sub(
            "Gracias por rentar nuestro estudio. Esperamos que el espacio "
            "haya sido perfecto para su evento. Su opinion nos ayuda a seguir "
            "mejorando y a que otros encuentren nuestro estudio."
        )
        c += _callout(
            "Si tuvo una buena experiencia, una resena en Google nos ayudaria mucho.",
            "#2e7d32", "#f0f8f0",
        )
        c += _review_btn("Dejar una Resena")

    else:
        subject = "How was your studio rental? -- Garcia Folklorico Studio"
        preheader = "We'd love to hear about your studio rental experience."

        c = _heading(f"Hi {name}!")
        c += _sub(
            "Thank you for renting our studio. We hope the space was perfect "
            "for your event. Your feedback helps us improve and helps others "
            "find our studio."
        )
        c += _callout(
            "If you had a great experience, a Google review would mean a lot to us.",
            "#2e7d32", "#f0f8f0",
        )
        c += _review_btn("Leave a Review")

    html = _email(c, preheader=preheader)
    return subject, html


def send_review_request(entry: dict, dry_run: bool = False) -> dict:
    """Send a review request email. Returns result dict."""
    if entry["type"] == "class":
        subject, html = build_class_review_email(entry)
    else:
        subject, html = build_rental_review_email(entry)

    if dry_run:
        return {"mode": "dry_run", "to": entry["email"], "subject": subject}

    success = send_email_sync(entry["email"], subject, html)
    return {
        "mode": "sent" if success else "failed",
        "to": entry["email"],
        "subject": subject,
    }
