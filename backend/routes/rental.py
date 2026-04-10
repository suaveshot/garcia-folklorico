from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from datetime import date, time
from models import get_db, RentalBooking
from routes.schedule import get_active_block, DAY_NAMES_EN, DAY_NAMES_ES
from services.availability import get_rental_availability
from services.email import send_rental_confirmation, send_rental_notification
from services.events import publish_event
from config import (
    RENTAL_RATE_STANDARD, RENTAL_RATE_DISCOUNT, RENTAL_DISCOUNT_THRESHOLD,
    RENTAL_MIN_HOURS, RENTAL_MAX_HOURS, STUDIO_OPEN_HOUR, STUDIO_CLOSE_HOUR
)
from schemas import RentalBookingIn

router = APIRouter()


def calculate_price(hours: int) -> tuple[float, float]:
    """Return (rate_per_hour, total_price)."""
    rate = RENTAL_RATE_DISCOUNT if hours >= RENTAL_DISCOUNT_THRESHOLD else RENTAL_RATE_STANDARD
    return rate, rate * hours


@router.get("/rentals/availability")
def rental_availability(
    date_str: str = Query(..., alias="date", description="YYYY-MM-DD"),
    db: Session = Depends(get_db)
):
    try:
        target_date = date.fromisoformat(date_str)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.")

    if target_date < date.today():
        raise HTTPException(status_code=400, detail="Cannot check availability for past dates.")

    block = get_active_block(db)
    hours = get_rental_availability(db, target_date, block)
    dow = target_date.weekday()

    return {
        "date": target_date.isoformat(),
        "day_name_en": DAY_NAMES_EN[dow],
        "day_name_es": DAY_NAMES_ES[dow],
        "hours": hours,
        "studio_open": STUDIO_OPEN_HOUR,
        "studio_close": STUDIO_CLOSE_HOUR,
        "pricing": {
            "standard_rate": RENTAL_RATE_STANDARD,
            "discount_rate": RENTAL_RATE_DISCOUNT,
            "discount_threshold": RENTAL_DISCOUNT_THRESHOLD,
            "min_hours": RENTAL_MIN_HOURS,
            "max_hours": RENTAL_MAX_HOURS,
        }
    }


@router.post("/rentals/book")
async def book_rental(data: RentalBookingIn, db: Session = Depends(get_db)):
    # Validate hours
    hours = data.end_hour - data.start_hour
    if hours < RENTAL_MIN_HOURS or hours > RENTAL_MAX_HOURS:
        raise HTTPException(
            status_code=400,
            detail=f"Rental must be between {RENTAL_MIN_HOURS} and {RENTAL_MAX_HOURS} hours."
        )

    if data.start_hour < STUDIO_OPEN_HOUR or data.end_hour > STUDIO_CLOSE_HOUR:
        raise HTTPException(status_code=400, detail="Hours outside studio operating hours.")

    if data.date < date.today():
        raise HTTPException(status_code=400, detail="Cannot book for past dates.")

    # Check availability for each hour in the range
    block = get_active_block(db)
    availability = get_rental_availability(db, data.date, block)
    avail_map = {h["hour"]: h for h in availability}

    for h in range(data.start_hour, data.end_hour):
        slot = avail_map.get(h)
        if not slot or not slot["available"]:
            reason = slot["reason"] if slot else "outside hours"
            raise HTTPException(
                status_code=409,
                detail=f"Hour {h}:00 is not available (reason: {reason})."
            )

    rate, total = calculate_price(hours)

    booking = RentalBooking(
        date=data.date,
        start_time=time(data.start_hour, 0),
        end_time=time(data.end_hour, 0),
        hours=hours,
        total_price=total,
        renter_name=data.renter_name,
        phone=data.phone,
        email=data.email,
        purpose=data.purpose,
        status="confirmed",
        language=data.language,
    )
    db.add(booking)
    db.commit()
    db.refresh(booking)

    result = {
        "id": booking.id,
        "date": booking.date.isoformat(),
        "start_time": booking.start_time.strftime("%I:%M %p").lstrip("0"),
        "end_time": booking.end_time.strftime("%I:%M %p").lstrip("0"),
        "hours": hours,
        "rate_per_hour": rate,
        "total_price": total,
        "renter_name": data.renter_name,
        "status": "confirmed",
        "message_en": f"Studio rental confirmed for {data.date.isoformat()}, {booking.start_time.strftime('%I:%M %p').lstrip('0')} - {booking.end_time.strftime('%I:%M %p').lstrip('0')} ({hours} hrs, ${total:.0f}). A confirmation email has been sent to {data.email}.",
        "message_es": f"Renta del estudio confirmada para {data.date.isoformat()}, {booking.start_time.strftime('%I:%M %p').lstrip('0')} - {booking.end_time.strftime('%I:%M %p').lstrip('0')} ({hours} hrs, ${total:.0f}). Se ha enviado un correo de confirmación a {data.email}.",
    }

    publish_event("rental", "booked", {
        "booking_id": booking.id,
        "date": str(booking.date),
        "start_time": booking.start_time.strftime("%I:%M %p").lstrip("0"),
        "end_time": booking.end_time.strftime("%I:%M %p").lstrip("0"),
        "hours": booking.hours,
        "total_price": booking.total_price,
        "renter_name": booking.renter_name,
        "phone": booking.phone,
        "email": booking.email,
        "purpose": booking.purpose,
        "language": booking.language,
    })

    try:
        await send_rental_confirmation(booking)
        await send_rental_notification(booking)
    except Exception as e:
        print(f"Email send failed: {e}")

    return result
