import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from models import Parent, PasswordReset, RefreshToken, get_db
from services.auth import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    hash_token,
    generate_verification_code,
    validate_password,
    check_rate_limit,
    record_failed_attempt,
    clear_rate_limit,
    decode_access_token,
)
from services.events import publish_event

# ── Email service (graceful fallback if not yet implemented) ─────────
try:
    from services.email import send_verification_email, send_password_reset_email
except ImportError:
    async def send_verification_email(parent):
        print(f"[EMAIL STUB] send_verification_email to {parent.email}")

    async def send_password_reset_email(parent, token):
        print(f"[EMAIL STUB] send_password_reset_email to {parent.email}")


router = APIRouter()


# ── Request schemas ──────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email: str
    password: str
    name: str
    phone: str
    language: str = "en"


class VerifyEmailRequest(BaseModel):
    email: str
    code: str


class LoginRequest(BaseModel):
    email: str
    password: str
    remember_me: bool = False


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


# ── POST /api/auth/register ──────────────────────────────────────────

@router.post("/auth/register", status_code=201)
async def register(data: RegisterRequest, db: Session = Depends(get_db)):
    # Check duplicate email
    existing = db.query(Parent).filter(Parent.email == data.email).first()
    if existing:
        raise HTTPException(status_code=409, detail="An account with this email already exists.")

    # Validate password
    valid, error_msg = validate_password(data.password)
    if not valid:
        raise HTTPException(status_code=400, detail=error_msg)

    # Generate verification code
    code, expires_at = generate_verification_code()

    # Create parent record
    parent = Parent(
        email=data.email,
        password_hash=hash_password(data.password),
        name=data.name,
        phone=data.phone,
        language=data.language,
        email_verified=0,
        verification_code=code,
        verification_expires=expires_at,
    )
    db.add(parent)
    db.commit()
    db.refresh(parent)

    publish_event("auth", "registered", {
        "parent_id": parent.id,
        "email": parent.email,
        "name": parent.name,
    })

    # Send verification email (non-fatal if it fails)
    try:
        await send_verification_email(parent)
    except Exception as e:
        print(f"[auth/register] Verification email failed: {e}")

    return {
        "message": "Account created. Check your email for verification code.",
        "parent_id": parent.id,
    }


# ── POST /api/auth/verify-email ──────────────────────────────────────

@router.post("/auth/verify-email")
def verify_email(data: VerifyEmailRequest, db: Session = Depends(get_db)):
    parent = db.query(Parent).filter(Parent.email == data.email).first()
    if not parent:
        raise HTTPException(status_code=404, detail="Account not found.")

    if parent.email_verified:
        return {"message": "Email already verified."}

    if parent.verification_code != data.code:
        raise HTTPException(status_code=400, detail="Invalid verification code.")

    # Check expiry (verification_expires stored as naive UTC)
    now = datetime.utcnow()
    if parent.verification_expires is None or now > parent.verification_expires:
        raise HTTPException(status_code=400, detail="Verification code has expired.")

    parent.email_verified = 1
    parent.verification_code = None
    parent.verification_expires = None
    db.commit()

    publish_event("auth", "email_verified", {
        "parent_id": parent.id,
        "email": parent.email,
    })

    return {"message": "Email verified successfully."}


# ── POST /api/auth/login ─────────────────────────────────────────────

@router.post("/auth/login")
def login(data: LoginRequest, db: Session = Depends(get_db)):
    # Rate limit check
    allowed, seconds_remaining = check_rate_limit(data.email)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Too many failed attempts. Try again in {seconds_remaining} seconds.",
        )

    parent = db.query(Parent).filter(Parent.email == data.email).first()
    if not parent:
        record_failed_attempt(data.email)
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    if not verify_password(data.password, parent.password_hash):
        record_failed_attempt(data.email)
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    if not parent.email_verified:
        raise HTTPException(status_code=403, detail="Please verify your email first.")

    # Successful login — clear rate limit
    clear_rate_limit(data.email)

    # Issue tokens
    access_token = create_access_token(parent.id)
    raw_refresh, refresh_hash = create_refresh_token(parent.id, remember_me=data.remember_me)

    days = 90 if data.remember_me else 30
    expires_at = datetime.utcnow() + timedelta(days=days)

    refresh_record = RefreshToken(
        parent_id=parent.id,
        token_hash=refresh_hash,
        expires_at=expires_at,
        revoked=0,
    )
    db.add(refresh_record)
    db.commit()

    publish_event("auth", "login", {
        "parent_id": parent.id,
        "email": parent.email,
    })

    return {
        "access_token": access_token,
        "refresh_token": raw_refresh,
        "parent_id": parent.id,
        "name": parent.name,
    }


# ── POST /api/auth/refresh ───────────────────────────────────────────

@router.post("/auth/refresh")
def refresh_token(data: RefreshRequest, db: Session = Depends(get_db)):
    # Decode JWT to extract parent_id (also validates signature/expiry)
    payload = decode_access_token(data.refresh_token)
    if payload is None:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token.")

    parent_id = payload.get("parent_id")
    if not parent_id:
        raise HTTPException(status_code=401, detail="Malformed refresh token.")

    # Find the stored token by hash
    token_hash = hash_token(data.refresh_token)
    now = datetime.utcnow()

    record = (
        db.query(RefreshToken)
        .filter(
            RefreshToken.token_hash == token_hash,
            RefreshToken.revoked == 0,
            RefreshToken.expires_at > now,
        )
        .first()
    )
    if not record:
        raise HTTPException(status_code=401, detail="Refresh token not found or revoked.")

    # Issue new access token
    access_token = create_access_token(parent_id)

    return {"access_token": access_token}


# ── POST /api/auth/logout ────────────────────────────────────────────

@router.post("/auth/logout")
def logout(data: LogoutRequest, db: Session = Depends(get_db)):
    token_hash = hash_token(data.refresh_token)

    record = (
        db.query(RefreshToken)
        .filter(RefreshToken.token_hash == token_hash)
        .first()
    )
    if record:
        record.revoked = 1
        db.commit()

    return {"message": "Logged out."}


# ── POST /api/auth/forgot-password ──────────────────────────────────

@router.post("/auth/forgot-password")
async def forgot_password(data: ForgotPasswordRequest, db: Session = Depends(get_db)):
    # Always return the same message to prevent email enumeration
    parent = db.query(Parent).filter(Parent.email == data.email).first()

    if parent:
        raw_token = secrets.token_urlsafe(32)
        token_hash = hash_token(raw_token)
        expires_at = datetime.utcnow() + timedelta(hours=1)

        reset_record = PasswordReset(
            parent_id=parent.id,
            token_hash=token_hash,
            expires_at=expires_at,
            used=0,
        )
        db.add(reset_record)
        db.commit()

        publish_event("auth", "password_reset_requested", {
            "parent_id": parent.id,
            "email": parent.email,
        })

        try:
            await send_password_reset_email(parent, raw_token)
        except Exception as e:
            print(f"[auth/forgot-password] Reset email failed: {e}")

    return {"message": "If an account exists, we sent a reset link."}


# ── POST /api/auth/reset-password ───────────────────────────────────

@router.post("/auth/reset-password")
def reset_password(data: ResetPasswordRequest, db: Session = Depends(get_db)):
    token_hash = hash_token(data.token)
    now = datetime.utcnow()

    reset_record = (
        db.query(PasswordReset)
        .filter(
            PasswordReset.token_hash == token_hash,
            PasswordReset.used == 0,
            PasswordReset.expires_at > now,
        )
        .first()
    )
    if not reset_record:
        raise HTTPException(status_code=400, detail="Reset token is invalid or has expired.")

    # Validate new password
    valid, error_msg = validate_password(data.new_password)
    if not valid:
        raise HTTPException(status_code=400, detail=error_msg)

    # Update password
    parent = db.query(Parent).filter(Parent.id == reset_record.parent_id).first()
    if not parent:
        raise HTTPException(status_code=404, detail="Account not found.")

    parent.password_hash = hash_password(data.new_password)

    # Mark reset token as used
    reset_record.used = 1

    # Revoke all refresh tokens for this parent (session invalidation)
    db.query(RefreshToken).filter(RefreshToken.parent_id == parent.id).update({"revoked": 1})

    db.commit()

    publish_event("auth", "password_reset", {
        "parent_id": parent.id,
        "email": parent.email,
    })

    return {"message": "Password reset successfully."}
