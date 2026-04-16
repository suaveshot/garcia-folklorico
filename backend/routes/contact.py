"""
Contact form endpoint.

Accepts a POST from the website's contact form, validates, rate-limits by IP,
and emails STUDIO_EMAIL (or CONTACT_TEST_RECIPIENT override) via the existing
SMTP helpers.

No DB write — inbound inquiries only. Add a ContactSubmission model if lead
tracking is ever wanted.
"""

import re as _re

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, timedelta
from config import STUDIO_EMAIL, CONTACT_TEST_RECIPIENT
from services.email import (
    _send_email, _email, _heading, _sub,
    _section_header, _detail_table, _detail_row, _callout,
)


router = APIRouter()

# In-memory rate limit: max 5 per IP per hour. Resets on restart (fine for a
# studio site without Redis).
_RATE_BUCKET: dict[str, list[datetime]] = {}
_RATE_WINDOW = timedelta(hours=1)
_RATE_MAX = 5


def _rate_ok(ip: str) -> bool:
    now = datetime.utcnow()
    hits = [t for t in _RATE_BUCKET.get(ip, []) if now - t < _RATE_WINDOW]
    if len(hits) >= _RATE_MAX:
        _RATE_BUCKET[ip] = hits
        return False
    hits.append(now)
    _RATE_BUCKET[ip] = hits
    return True


class ContactIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: str = Field(min_length=3, max_length=254)
    phone: Optional[str] = Field(default=None, max_length=40)
    inquiry: Optional[str] = Field(default="other", max_length=60)
    message: Optional[str] = Field(default="", max_length=4000)
    gotcha: Optional[str] = Field(default=None, alias="_gotcha")
    language: Optional[str] = Field(default="en", max_length=4)


INQUIRY_LABELS = {
    "events": "Events & Performances",
    "partnerships": "Partnerships",
    "other": "Other",
}


@router.post("/contact")
async def contact_submit(payload: ContactIn, request: Request):
    # Honeypot — bots fill this, return 200 so the trap stays invisible
    if payload.gotcha:
        return {"ok": True}

    # Basic email shape check (EmailStr dep not installed in this image)
    if not _re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", payload.email):
        raise HTTPException(status_code=422, detail="Invalid email address.")

    client_ip = request.client.host if request.client else "unknown"
    if not _rate_ok(client_ip):
        raise HTTPException(status_code=429, detail="Too many submissions. Try again later.")

    recipient = CONTACT_TEST_RECIPIENT or STUDIO_EMAIL
    if not recipient:
        raise HTTPException(status_code=503, detail="Contact form is temporarily unavailable.")

    inquiry_label = INQUIRY_LABELS.get(payload.inquiry or "other", "Other")
    safe_message = (payload.message or "").strip().replace("<", "&lt;").replace(">", "&gt;")
    safe_message_html = safe_message.replace("\n", "<br>") or "<em>(no message provided)</em>"

    test_marker = "[TEST] " if CONTACT_TEST_RECIPIENT else ""
    subject = f"{test_marker}Website contact: {payload.name} · {inquiry_label}"
    preheader = f"{test_marker}New inquiry from {payload.name} about {inquiry_label}"

    c = _heading("New Contact Form Submission")
    c += _sub(f"<strong>{payload.name}</strong> · {inquiry_label}")
    if CONTACT_TEST_RECIPIENT:
        c += _callout(
            "This is a test-mode email. "
            "Contact form is being verified before the first real send.",
            "#4A154B", "#f8f0ff",
        )
    c += _section_header("Sender")
    c += _detail_table(
        _detail_row("Name", f"<strong>{payload.name}</strong>"),
        _detail_row("Email", f"<a href='mailto:{payload.email}' style='color:#E8620A;text-decoration:none;'>{payload.email}</a>"),
        _detail_row("Phone", payload.phone or "—"),
        _detail_row("Topic", inquiry_label),
    )
    c += _section_header("Message")
    c += _callout(safe_message_html)

    await _send_email(recipient, subject, _email(c, preheader))
    return {"ok": True}
