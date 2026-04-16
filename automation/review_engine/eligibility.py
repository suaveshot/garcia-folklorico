"""
Garcia Folklorico Studio -- Review Eligibility Checker
Determines which parents and rental clients are eligible for a review request.

Rules:
- Class parents: 3+ days after block end_date, status=registered, not asked in 90 days
- Rental clients: 2+ days after confirmed rental, not asked in 90 days
- Same email never asked more than once per 90 days
"""

import json
import os
from datetime import datetime, date, timedelta
from pathlib import Path

STATE_FILE = Path(__file__).parent / "review_state.json"
COOLDOWN_DAYS = 90
CLASS_DELAY_DAYS = 1
RENTAL_DELAY_DAYS = 1


def load_state() -> dict:
    if STATE_FILE.exists():
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"requests": {}}


def save_state(state: dict):
    tmp = str(STATE_FILE) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, default=str)
    os.replace(tmp, str(STATE_FILE))


def _is_cooled_down(state: dict, email: str) -> bool:
    """Check if enough time has passed since last ask for this email."""
    entry = state.get("requests", {}).get(email)
    if not entry:
        return True
    last_asked = datetime.fromisoformat(entry["last_asked"])
    return (datetime.now() - last_asked).days >= COOLDOWN_DAYS


def find_eligible_parents(db, state: dict) -> list:
    """Find parents from completed blocks who haven't been asked recently."""
    from models import Registration, Block, ClassType

    today = date.today()
    cutoff = today - timedelta(days=CLASS_DELAY_DAYS)

    # Blocks that ended at least CLASS_DELAY_DAYS ago
    completed_blocks = db.query(Block).filter(
        Block.end_date <= cutoff,
    ).all()

    eligible = []
    for block in completed_blocks:
        registrations = db.query(Registration).filter(
            Registration.block_id == block.id,
            Registration.status == "registered",
        ).all()

        for reg in registrations:
            if not _is_cooled_down(state, reg.email):
                continue

            ct = db.query(ClassType).filter_by(id=reg.class_type_id).first()
            eligible.append({
                "type": "class",
                "email": reg.email,
                "parent_name": reg.parent_name,
                "child_name": reg.child_name,
                "class_name_en": ct.name_en if ct else "Class",
                "class_name_es": ct.name_es if ct else "Clase",
                "block_name": block.name,
                "language": reg.language,
            })

    # Deduplicate by email (parent may have multiple children)
    seen = set()
    deduped = []
    for e in eligible:
        if e["email"] not in seen:
            seen.add(e["email"])
            deduped.append(e)

    return deduped


def find_eligible_renters(db, state: dict) -> list:
    """Find rental clients from 2+ days ago who haven't been asked recently."""
    from models import RentalBooking

    today = date.today()
    cutoff = today - timedelta(days=RENTAL_DELAY_DAYS)

    rentals = db.query(RentalBooking).filter(
        RentalBooking.date <= cutoff,
        RentalBooking.status == "confirmed",
    ).all()

    eligible = []
    seen = set()
    for rental in rentals:
        if rental.email in seen:
            continue
        if not _is_cooled_down(state, rental.email):
            continue
        seen.add(rental.email)
        eligible.append({
            "type": "rental",
            "email": rental.email,
            "renter_name": rental.renter_name,
            "rental_date": rental.date.isoformat(),
            "language": rental.language,
        })

    return eligible


def find_all_eligible(db) -> tuple:
    """Return (eligible_list, state) for both parents and renters."""
    state = load_state()
    parents = find_eligible_parents(db, state)
    renters = find_eligible_renters(db, state)
    return parents + renters, state
