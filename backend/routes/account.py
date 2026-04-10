from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from models import Parent, Registration, RentalBooking, RefreshToken, ClassType, Block, get_db
from services.auth import (
    get_current_parent,
    hash_password,
    verify_password,
    validate_password,
    generate_verification_code,
    hash_token,
)
from services.events import publish_event

# ── Email service (graceful fallback if not yet implemented) ─────────
try:
    from services.email import send_verification_email
except ImportError:
    async def send_verification_email(parent):
        print(f"[EMAIL STUB] send_verification_email to {parent.email}")


router = APIRouter()


# ── Request schemas ──────────────────────────────────────────────────

class UpdateProfileRequest(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    language: Optional[str] = None


class UpdatePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class UpdateEmailRequest(BaseModel):
    current_password: str
    new_email: str


# ── GET /api/account/dashboard ───────────────────────────────────────

@router.get("/account/dashboard")
def get_dashboard(
    current_parent: Parent = Depends(get_current_parent),
    db: Session = Depends(get_db),
):
    # Registrations: join ClassType + Block, exclude cancelled
    registrations_raw = (
        db.query(Registration, ClassType, Block)
        .join(ClassType, Registration.class_type_id == ClassType.id)
        .join(Block, Registration.block_id == Block.id)
        .filter(
            Registration.parent_id == current_parent.id,
            Registration.status != "cancelled",
        )
        .order_by(Registration.created_at.desc())
        .all()
    )

    registrations = [
        {
            "id": reg.id,
            "child_name": reg.child_name,
            "class_name_en": ct.name_en,
            "class_name_es": ct.name_es,
            "block_name": block.name,
            "status": reg.status,
            "payment_status": reg.payment_status,
            "created_at": reg.created_at.isoformat() if reg.created_at else None,
        }
        for reg, ct, block in registrations_raw
    ]

    # Rental bookings
    rentals_raw = (
        db.query(RentalBooking)
        .filter(RentalBooking.parent_id == current_parent.id)
        .order_by(RentalBooking.created_at.desc())
        .all()
    )

    rentals = [
        {
            "id": r.id,
            "date": r.date.isoformat() if r.date else None,
            "start_time": r.start_time.strftime("%H:%M") if r.start_time else None,
            "end_time": r.end_time.strftime("%H:%M") if r.end_time else None,
            "hours": r.hours,
            "total_price": r.total_price,
            "renter_name": r.renter_name,
            "status": r.status,
            "payment_status": r.payment_status,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rentals_raw
    ]

    return {
        "parent": {
            "id": current_parent.id,
            "name": current_parent.name,
            "email": current_parent.email,
            "phone": current_parent.phone,
            "language": current_parent.language,
        },
        "registrations": registrations,
        "rentals": rentals,
    }


# ── PUT /api/account/profile ─────────────────────────────────────────

@router.put("/account/profile")
def update_profile(
    data: UpdateProfileRequest,
    current_parent: Parent = Depends(get_current_parent),
    db: Session = Depends(get_db),
):
    if data.name is not None:
        current_parent.name = data.name
    if data.phone is not None:
        current_parent.phone = data.phone
    if data.language is not None:
        current_parent.language = data.language

    db.commit()

    publish_event("account", "profile_updated", {
        "parent_id": current_parent.id,
        "email": current_parent.email,
    })

    return {"message": "Profile updated."}


# ── PUT /api/account/password ─────────────────────────────────────────

@router.put("/account/password")
def update_password(
    data: UpdatePasswordRequest,
    current_parent: Parent = Depends(get_current_parent),
    db: Session = Depends(get_db),
):
    if not verify_password(data.current_password, current_parent.password_hash):
        raise HTTPException(status_code=401, detail="Current password is incorrect.")

    valid, error_msg = validate_password(data.new_password)
    if not valid:
        raise HTTPException(status_code=400, detail=error_msg)

    current_parent.password_hash = hash_password(data.new_password)

    # Revoke all refresh tokens for this parent
    db.query(RefreshToken).filter(RefreshToken.parent_id == current_parent.id).update({"revoked": 1})

    db.commit()

    publish_event("account", "password_changed", {
        "parent_id": current_parent.id,
        "email": current_parent.email,
    })

    return {"message": "Password changed. Please log in again."}


# ── PUT /api/account/email ─────────────────────────────────────────────

@router.put("/account/email")
async def update_email(
    data: UpdateEmailRequest,
    current_parent: Parent = Depends(get_current_parent),
    db: Session = Depends(get_db),
):
    if not verify_password(data.current_password, current_parent.password_hash):
        raise HTTPException(status_code=401, detail="Current password is incorrect.")

    existing = db.query(Parent).filter(Parent.email == data.new_email).first()
    if existing:
        raise HTTPException(status_code=409, detail="Email address is already in use.")

    code, expires_at = generate_verification_code()

    current_parent.email = data.new_email
    current_parent.email_verified = 0
    current_parent.verification_code = code
    current_parent.verification_expires = expires_at

    db.commit()
    db.refresh(current_parent)

    publish_event("account", "email_changed", {
        "parent_id": current_parent.id,
        "new_email": data.new_email,
    })

    try:
        await send_verification_email(current_parent)
    except Exception as e:
        print(f"[account/email] Verification email failed: {e}")

    return {"message": "Verification code sent to new email."}
