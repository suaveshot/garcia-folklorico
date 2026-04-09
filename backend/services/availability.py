from datetime import date, time
from sqlalchemy.orm import Session
from models import Block, ClassSlot, RentalBooking
from config import STUDIO_OPEN_HOUR, STUDIO_CLOSE_HOUR


def get_rental_availability(db: Session, target_date: date, block: Block) -> list[dict]:
    """Return hour-by-hour availability for a given date.

    Each hour from STUDIO_OPEN_HOUR to STUDIO_CLOSE_HOUR-1 is returned with
    available=True/False and a reason if unavailable.
    """
    day_of_week = target_date.weekday()  # 0=Monday

    # Get class slots for this day
    class_slots = (
        db.query(ClassSlot)
        .filter_by(block_id=block.id, day_of_week=day_of_week)
        .all()
    )

    # Get existing rental bookings for this date
    rental_bookings = (
        db.query(RentalBooking)
        .filter(
            RentalBooking.date == target_date,
            RentalBooking.status == "confirmed"
        )
        .all()
    )

    # Build set of blocked hours
    blocked = {}  # hour -> reason

    for slot in class_slots:
        start_h = slot.start_time.hour
        end_h = slot.end_time.hour
        # If end_time has minutes (e.g., 11:30), the hour is still partially occupied
        if slot.end_time.minute > 0:
            end_h += 1
        for h in range(start_h, end_h):
            blocked[h] = "class"

    for booking in rental_bookings:
        start_h = booking.start_time.hour
        end_h = booking.end_time.hour
        for h in range(start_h, end_h):
            blocked[h] = "booked"

    # Build availability list
    hours = []
    for h in range(STUDIO_OPEN_HOUR, STUDIO_CLOSE_HOUR):
        t = time(h, 0)
        label = t.strftime("%I:%M %p").lstrip("0")
        reason = blocked.get(h)
        hours.append({
            "hour": h,
            "label": label,
            "available": reason is None,
            "reason": reason,
        })

    return hours
