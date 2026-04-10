import os
import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from models import Parent, get_db

# ── JWT Secret ───────────────────────────────────────────────────────

JWT_SECRET = os.getenv("JWT_SECRET", secrets.token_hex(32))
JWT_ALGORITHM = "HS256"


# ── Password Hashing ─────────────────────────────────────────────────

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


# ── Token Hashing ────────────────────────────────────────────────────

def hash_token(token: str) -> str:
    """SHA-256 hash a raw token for safe DB storage."""
    return hashlib.sha256(token.encode()).hexdigest()


# ── JWT Access Token ─────────────────────────────────────────────────

def create_access_token(parent_id: int) -> str:
    expiry = datetime.now(timezone.utc) + timedelta(minutes=15)
    payload = {"parent_id": parent_id, "exp": expiry}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict | None:
    """Decode and validate an access token. Returns payload dict or None."""
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


# ── JWT Refresh Token ────────────────────────────────────────────────

def create_refresh_token(
    parent_id: int, remember_me: bool = False
) -> tuple[str, str]:
    """
    Returns (raw_token, token_hash).
    Expiry: 90 days with remember_me, 30 days otherwise.
    """
    days = 90 if remember_me else 30
    expiry = datetime.now(timezone.utc) + timedelta(days=days)
    raw_token = secrets.token_hex(64)
    payload = {"parent_id": parent_id, "exp": expiry, "jti": raw_token}
    signed = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return signed, hash_token(signed)


# ── Email Verification ───────────────────────────────────────────────

def generate_verification_code() -> tuple[str, datetime]:
    """
    Returns (6-digit code string, expires_at datetime).
    Code expires in 1 hour.
    """
    code = str(secrets.randbelow(900000) + 100000)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
    return code, expires_at


# ── Password Validation ──────────────────────────────────────────────

def validate_password(password: str) -> tuple[bool, str]:
    """
    Returns (valid, error_message).
    Rules: min 8 chars, at least one letter, at least one digit.
    """
    if len(password) < 8:
        return False, "Password must be at least 8 characters."
    if not any(c.isalpha() for c in password):
        return False, "Password must contain at least one letter."
    if not any(c.isdigit() for c in password):
        return False, "Password must contain at least one number."
    return True, ""


# ── Rate Limiting (in-memory) ────────────────────────────────────────

_rate_limit_store: dict[str, dict] = {}
# Structure: { email: { "attempts": int, "locked_until": datetime | None } }

_MAX_ATTEMPTS = 5
_LOCKOUT_SECONDS = 15 * 60  # 15 minutes


def check_rate_limit(email: str) -> tuple[bool, int]:
    """
    Returns (allowed, seconds_remaining).
    allowed=False when the account is locked out.
    seconds_remaining is 0 when allowed.
    """
    entry = _rate_limit_store.get(email)
    if not entry:
        return True, 0

    locked_until = entry.get("locked_until")
    if locked_until:
        now = datetime.now(timezone.utc)
        # locked_until may be naive if stored without tz; normalise
        if locked_until.tzinfo is None:
            locked_until = locked_until.replace(tzinfo=timezone.utc)
        if now < locked_until:
            remaining = int((locked_until - now).total_seconds())
            return False, remaining
        # Lockout expired -- reset
        _rate_limit_store.pop(email, None)

    return True, 0


def record_failed_attempt(email: str) -> None:
    """Increment failed attempt counter; apply lockout after MAX_ATTEMPTS."""
    entry = _rate_limit_store.setdefault(
        email, {"attempts": 0, "locked_until": None}
    )
    entry["attempts"] += 1
    if entry["attempts"] >= _MAX_ATTEMPTS:
        entry["locked_until"] = datetime.now(timezone.utc) + timedelta(
            seconds=_LOCKOUT_SECONDS
        )


def clear_rate_limit(email: str) -> None:
    """Remove rate limit entry on successful login."""
    _rate_limit_store.pop(email, None)


# ── FastAPI Dependency ───────────────────────────────────────────────

def get_current_parent(
    request: Request, db: Session = Depends(get_db)
) -> Parent:
    """
    FastAPI dependency.  Extracts Bearer token from Authorization header,
    validates it, and returns the Parent ORM object.
    Raises HTTP 401 if the token is missing, invalid, or the parent
    no longer exists.
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header.")

    token = auth_header[len("Bearer "):]
    payload = decode_access_token(token)
    if payload is None:
        raise HTTPException(status_code=401, detail="Token is invalid or expired.")

    parent_id = payload.get("parent_id")
    if not parent_id:
        raise HTTPException(status_code=401, detail="Token payload is malformed.")

    parent = db.query(Parent).filter(Parent.id == parent_id).first()
    if parent is None:
        raise HTTPException(status_code=401, detail="Account not found.")

    return parent
