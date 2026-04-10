import os
import stripe
from fastapi import APIRouter, Request, Depends, HTTPException
from sqlalchemy.orm import Session
from models import Registration, RentalBooking, ClassType, get_db
from services.auth import get_current_parent
from services.events import publish_event

router = APIRouter()

STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
SITE_URL = os.getenv("SITE_URL", "https://garciafolklorico.com")

if STRIPE_SECRET_KEY:
    stripe.api_key = STRIPE_SECRET_KEY


@router.post("/payments/create-checkout")
async def create_checkout(
    data: dict,
    parent=Depends(get_current_parent),
    db: Session = Depends(get_db),
):
    if not STRIPE_SECRET_KEY:
        raise HTTPException(status_code=400, detail="Online payments not configured")

    record_type = data.get("type")
    record_id = data.get("id")

    if record_type not in ("registration", "rental"):
        raise HTTPException(status_code=400, detail="type must be 'registration' or 'rental'")
    if not isinstance(record_id, int):
        raise HTTPException(status_code=400, detail="id must be an integer")

    if record_type == "registration":
        record = db.query(Registration).filter_by(id=record_id).first()
        if not record:
            raise HTTPException(status_code=404, detail="Registration not found")
        if record.parent_id != parent.id:
            raise HTTPException(status_code=403, detail="Not authorized")

        ct = db.query(ClassType).filter_by(id=record.class_type_id).first()
        description = ct.name_en if ct else "Class Registration"

        # block_fee comes from schedule_data.json via the class type key;
        # fall back to a generic lookup in the schedule_data at import time
        block_fee = _get_block_fee(ct.key if ct else None)
        amount_cents = int(block_fee * 100)

    else:  # rental
        record = db.query(RentalBooking).filter_by(id=record_id).first()
        if not record:
            raise HTTPException(status_code=404, detail="Rental booking not found")
        if record.parent_id != parent.id:
            raise HTTPException(status_code=403, detail="Not authorized")

        description = f"Studio Rental ({record.hours}hrs)"
        amount_cents = int(record.total_price * 100)

    # Create Stripe Checkout Session
    try:
        session = stripe.checkout.Session.create(
            line_items=[
                {
                    "price_data": {
                        "currency": "usd",
                        "unit_amount": amount_cents,
                        "product_data": {"name": description},
                    },
                    "quantity": 1,
                }
            ],
            mode="payment",
            success_url=f"{SITE_URL}/my-account?payment=success",
            cancel_url=f"{SITE_URL}/my-account?payment=cancelled",
            metadata={"type": record_type, "id": str(record_id)},
        )
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=502, detail=f"Stripe error: {e.user_message or str(e)}")

    # Save session ID on the record
    record.stripe_session_id = session.id
    db.commit()

    return {"checkout_url": session.url}


@router.post("/webhooks/stripe")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    if not STRIPE_WEBHOOK_SECRET:
        raise HTTPException(status_code=400, detail="Webhooks not configured")

    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")

    try:
        event = stripe.Webhook.construct_event(payload, sig, STRIPE_WEBHOOK_SECRET)
    except (ValueError, stripe.error.SignatureVerificationError):
        raise HTTPException(status_code=400, detail="Invalid signature")

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        meta = session.get("metadata", {})
        record_type = meta.get("type")
        record_id_str = meta.get("id")

        if record_type and record_id_str:
            record_id = int(record_id_str)

            if record_type == "registration":
                record = db.query(Registration).filter_by(id=record_id).first()
            elif record_type == "rental":
                record = db.query(RentalBooking).filter_by(id=record_id).first()
            else:
                record = None

            if record:
                record.payment_status = "paid"
                record.payment_method = "card"
                db.commit()

                publish_event("payment", "received", {
                    "type": record_type,
                    "id": record_id,
                    "stripe_session_id": session.get("id"),
                    "amount_total": session.get("amount_total"),
                    "currency": session.get("currency"),
                })

    return {"status": "ok"}


# ── Helpers ──────────────────────────────────────────────────────────────────

_BLOCK_FEES = {
    "mommy_and_me": 120,
    "semillas": 120,
    "botones_de_flor": 140,
    "elementary": 150,
    "raices": 160,
}


def _get_block_fee(class_key: str | None) -> float:
    """Return the block tuition fee for a class type key."""
    if class_key and class_key in _BLOCK_FEES:
        return float(_BLOCK_FEES[class_key])
    # Default if key is unknown
    return 120.0
