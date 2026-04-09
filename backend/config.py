import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = os.getenv("DB_PATH", str(BASE_DIR / "database.db"))
DATABASE_URL = f"sqlite:///{DB_PATH}"

# Studio hours
STUDIO_OPEN_HOUR = 8   # 8 AM
STUDIO_CLOSE_HOUR = 22  # 10 PM

# Rental pricing
RENTAL_RATE_STANDARD = 75  # $/hr for 1-3 hours
RENTAL_RATE_DISCOUNT = 60  # $/hr for 4-6 hours
RENTAL_DISCOUNT_THRESHOLD = 4  # hours
RENTAL_MIN_HOURS = 1
RENTAL_MAX_HOURS = 6

# Waitlist
WAITLIST_CLAIM_HOURS = 48

# Email
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
STUDIO_EMAIL = os.getenv("STUDIO_EMAIL", "")  # Garcia's team email
FROM_EMAIL = os.getenv("FROM_EMAIL", "")

# CORS
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:8080,http://127.0.0.1:8080").split(",")
