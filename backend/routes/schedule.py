from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import date
from models import get_db, Block, ClassSlot, ClassType, Registration

router = APIRouter()

DAY_NAMES_EN = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
DAY_NAMES_ES = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]

MONTH_NAMES_EN = ["", "January", "February", "March", "April", "May", "June",
                  "July", "August", "September", "October", "November", "December"]
MONTH_NAMES_ES = ["", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
                  "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]


def format_date_en(d: date) -> str:
    return f"{MONTH_NAMES_EN[d.month]} {d.day}, {d.year}"


def format_date_es(d: date) -> str:
    return f"{d.day} de {MONTH_NAMES_ES[d.month]} {d.year}"


def get_active_block(db: Session) -> Block:
    block = db.query(Block).filter_by(status="active").first()
    if not block:
        raise HTTPException(status_code=404, detail="No active class block found")
    return block


def get_registered_count(db: Session, class_type_id: int, block_id: int) -> int:
    return db.query(Registration).filter(
        Registration.class_type_id == class_type_id,
        Registration.block_id == block_id,
        Registration.status == "registered"
    ).count()


@router.get("/blocks/current")
def current_block(db: Session = Depends(get_db)):
    block = get_active_block(db)
    return {
        "id": block.id,
        "name": block.name,
        "start_date": block.start_date.isoformat(),
        "end_date": block.end_date.isoformat(),
        "start_date_en": format_date_en(block.start_date),
        "start_date_es": format_date_es(block.start_date),
        "end_date_en": format_date_en(block.end_date),
        "end_date_es": format_date_es(block.end_date),
        "status": block.status,
    }


@router.get("/schedule")
def get_schedule(db: Session = Depends(get_db)):
    block = get_active_block(db)
    slots = (
        db.query(ClassSlot)
        .filter_by(block_id=block.id)
        .order_by(ClassSlot.day_of_week, ClassSlot.start_time)
        .all()
    )

    # Get registration counts per class type (not per slot)
    class_type_ids = {s.class_type_id for s in slots}
    reg_counts = {}
    for ct_id in class_type_ids:
        reg_counts[ct_id] = get_registered_count(db, ct_id, block.id)

    schedule_by_day = {}
    for slot in slots:
        day = slot.day_of_week
        ct = slot.class_type
        registered = reg_counts.get(ct.id, 0)
        remaining = ct.max_capacity - registered

        if day not in schedule_by_day:
            schedule_by_day[day] = {
                "day_of_week": day,
                "day_name_en": DAY_NAMES_EN[day],
                "day_name_es": DAY_NAMES_ES[day],
                "classes": []
            }

        schedule_by_day[day]["classes"].append({
            "slot_id": slot.id,
            "class_type_id": ct.id,
            "class_key": ct.key,
            "name_en": ct.name_en,
            "name_es": ct.name_es,
            "age_range_en": ct.age_range_text_en,
            "age_range_es": ct.age_range_text_es,
            "description_en": ct.description_en,
            "description_es": ct.description_es,
            "start_time": slot.start_time.strftime("%H:%M"),
            "end_time": slot.end_time.strftime("%H:%M"),
            "max_capacity": ct.max_capacity,
            "registered_count": registered,
            "spots_remaining": remaining,
            "is_full": remaining <= 0,
        })

    return {
        "block": {
            "id": block.id,
            "name": block.name,
            "start_date": block.start_date.isoformat(),
            "end_date": block.end_date.isoformat(),
            "start_date_en": format_date_en(block.start_date),
            "start_date_es": format_date_es(block.start_date),
            "end_date_en": format_date_en(block.end_date),
            "end_date_es": format_date_es(block.end_date),
        },
        "days": [schedule_by_day[d] for d in sorted(schedule_by_day.keys())]
    }


@router.get("/classes/{class_type_id}")
def get_class_detail(class_type_id: int, db: Session = Depends(get_db)):
    block = get_active_block(db)
    ct = db.query(ClassType).filter_by(id=class_type_id).first()
    if not ct:
        raise HTTPException(status_code=404, detail="Class type not found")

    slots = (
        db.query(ClassSlot)
        .filter_by(block_id=block.id, class_type_id=class_type_id)
        .order_by(ClassSlot.day_of_week, ClassSlot.start_time)
        .all()
    )

    registered = get_registered_count(db, class_type_id, block.id)
    remaining = ct.max_capacity - registered

    # Build schedule summary
    slot_strings_en = []
    slot_strings_es = []
    for s in slots:
        time_str = s.start_time.strftime("%I:%M %p").lstrip("0")
        slot_strings_en.append(f"{DAY_NAMES_EN[s.day_of_week]} {time_str}")
        slot_strings_es.append(f"{DAY_NAMES_ES[s.day_of_week]} {time_str}")

    return {
        "class_type": {
            "id": ct.id,
            "key": ct.key,
            "name_en": ct.name_en,
            "name_es": ct.name_es,
            "age_range_en": ct.age_range_text_en,
            "age_range_es": ct.age_range_text_es,
            "description_en": ct.description_en,
            "description_es": ct.description_es,
            "max_capacity": ct.max_capacity,
        },
        "block": {
            "id": block.id,
            "name": block.name,
            "start_date": block.start_date.isoformat(),
            "end_date": block.end_date.isoformat(),
            "start_date_en": format_date_en(block.start_date),
            "start_date_es": format_date_es(block.start_date),
            "end_date_en": format_date_en(block.end_date),
            "end_date_es": format_date_es(block.end_date),
        },
        "schedule_en": ", ".join(slot_strings_en),
        "schedule_es": ", ".join(slot_strings_es),
        "registered_count": registered,
        "spots_remaining": remaining,
        "is_full": remaining <= 0,
    }
