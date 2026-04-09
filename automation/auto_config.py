"""
Garcia Folklorico Studio -- Automation Config
Shared configuration for all automation tools.

All tools import this to get DB access, email sending, and path constants.
"""

import os
import sys
import asyncio
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path
from dotenv import load_dotenv

# Paths
AUTOMATION_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = AUTOMATION_DIR.parent
BACKEND_DIR = PROJECT_ROOT / "backend"

# Load backend .env
load_dotenv(BACKEND_DIR / ".env")

# Add backend to path so we can import models + email service
sys.path.insert(0, str(BACKEND_DIR))

# Re-export from backend config
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.hostinger.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
STUDIO_EMAIL = os.getenv("STUDIO_EMAIL", "")
FROM_EMAIL = os.getenv("FROM_EMAIL", "")

# Automation-specific
ALERT_EMAIL = os.getenv("ALERT_EMAIL", "salarcon@americalpatrol.com")
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")

# Google Sheets (populated later when Sam provides credentials)
GOOGLE_SHEETS_CREDS = os.getenv("GOOGLE_SHEETS_CREDS", "")
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "")

# Health + events directories
HEALTH_DIR = AUTOMATION_DIR / "watchdog"
EVENTS_DIR = AUTOMATION_DIR / "pipeline_events"


def get_db():
    """Get a SQLAlchemy session for read-only queries."""
    from models import SessionLocal
    return SessionLocal()


def send_email_sync(to: str, subject: str, html_body: str,
                    plain_text: str = None, ics_data: str = None):
    """
    Synchronous email sender for cron scripts.
    Reuses the same Hostinger SMTP config as the backend.
    """
    if not SMTP_USER or not SMTP_PASSWORD:
        print(f"[EMAIL SKIPPED] No SMTP credentials. Would send to {to}: {subject}")
        return False

    msg = MIMEMultipart("mixed")
    msg["From"] = f"Garcia Folklorico Studio <{FROM_EMAIL or SMTP_USER}>"
    msg["To"] = to
    msg["Subject"] = subject

    alt = MIMEMultipart("alternative")
    if plain_text:
        alt.attach(MIMEText(plain_text, "plain", "utf-8"))
    else:
        import re
        text = re.sub(r"<br\s*/?>", "\n", html_body, flags=re.IGNORECASE)
        text = re.sub(r"<[^>]+>", "", text)
        text = re.sub(r"&\w+;", "", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        alt.attach(MIMEText(text.strip(), "plain", "utf-8"))
    alt.attach(MIMEText(html_body, "html", "utf-8"))
    msg.attach(alt)

    if ics_data:
        ics_part = MIMEText(ics_data, "calendar", "utf-8")
        ics_part.add_header("Content-Disposition", "attachment", filename="event.ics")
        msg.attach(ics_part)

    try:
        if SMTP_PORT == 465:
            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=30) as server:
                server.login(SMTP_USER, SMTP_PASSWORD)
                server.send_message(msg)
        else:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as server:
                server.starttls()
                server.login(SMTP_USER, SMTP_PASSWORD)
                server.send_message(msg)
        return True
    except Exception as e:
        print(f"[EMAIL ERROR] Failed to send to {to}: {e}")
        return False
