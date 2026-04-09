"""Seed the database with block schedule data from schedule_data.json."""
import json
from datetime import date, time
from pathlib import Path
from models import init_db, SessionLocal, Block, ClassType, ClassSlot

DAY_MAP = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6
}


def parse_time(t: str) -> time:
    h, m = t.split(":")
    return time(int(h), int(m))


def seed():
    init_db()
    db = SessionLocal()

    data_path = Path(__file__).parent / "schedule_data.json"
    with open(data_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Upsert class types
    for key, ct in data["class_types"].items():
        existing = db.query(ClassType).filter_by(key=key).first()
        if existing:
            for attr, val in ct.items():
                setattr(existing, attr, val)
        else:
            db.add(ClassType(key=key, **ct))
    db.commit()

    # Deactivate old blocks
    block_data = data["block"]
    db.query(Block).filter(Block.status == "active").update({"status": "past"})
    db.commit()

    # Create new block
    block = Block(
        name=block_data["name"],
        start_date=date.fromisoformat(block_data["start_date"]),
        end_date=date.fromisoformat(block_data["end_date"]),
        status="active"
    )
    db.add(block)
    db.commit()

    # Create class slots
    class_type_map = {ct.key: ct.id for ct in db.query(ClassType).all()}
    for slot in data["slots"]:
        class_type_id = class_type_map[slot["class"]]
        db.add(ClassSlot(
            block_id=block.id,
            class_type_id=class_type_id,
            day_of_week=DAY_MAP[slot["day"]],
            start_time=parse_time(slot["start"]),
            end_time=parse_time(slot["end"])
        ))
    db.commit()

    # Summary
    print(f"Seeded block: {block.name} ({block.start_date} to {block.end_date})")
    print(f"Class types: {len(class_type_map)}")
    print(f"Class slots: {len(data['slots'])}")
    for key, ct_id in class_type_map.items():
        ct = db.get(ClassType, ct_id)
        slots = db.query(ClassSlot).filter_by(block_id=block.id, class_type_id=ct_id).count()
        print(f"  {ct.name_en}: {slots} slots/week, max {ct.max_capacity} students")

    db.close()


if __name__ == "__main__":
    seed()
