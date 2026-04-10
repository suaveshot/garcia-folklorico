from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from models import get_db, Block, ClassType, Registration
from schemas import RegistrationIn
from routes.schedule import get_active_block, get_registered_count, DAY_NAMES_EN, DAY_NAMES_ES, format_date_en, format_date_es
from services.email import send_registration_email, send_registration_notification
from services.events import publish_event

router = APIRouter()


@router.post("/classes/register")
async def register_for_class(data: RegistrationIn, db: Session = Depends(get_db)):
    block = get_active_block(db)

    ct = db.query(ClassType).filter_by(id=data.class_type_id).first()
    if not ct:
        raise HTTPException(status_code=404, detail="Class type not found")

    # Check capacity
    registered_count = get_registered_count(db, ct.id, block.id)
    is_full = registered_count >= ct.max_capacity

    # Check for duplicate registration (same child + class + block)
    existing = db.query(Registration).filter(
        Registration.class_type_id == ct.id,
        Registration.block_id == block.id,
        Registration.child_name == data.child_name,
        Registration.email == data.email,
        Registration.status.in_(["registered", "waitlisted"])
    ).first()
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"A registration for {data.child_name} in {ct.name_en} already exists (status: {existing.status})"
        )

    status = "waitlisted" if is_full else "registered"

    reg = Registration(
        class_type_id=ct.id,
        block_id=block.id,
        parent_name=data.parent_name,
        child_name=data.child_name,
        child_age=data.child_age,
        phone=data.phone,
        email=data.email,
        emergency_contact=data.emergency_contact,
        status=status,
        language=data.language,
    )
    db.add(reg)
    db.commit()
    db.refresh(reg)

    # Link or create parent account (optional - only if password provided)
    if data.password:
        from services.auth import hash_password, validate_password, generate_verification_code
        from models import Parent

        existing_parent = db.query(Parent).filter_by(email=data.email).first()
        if existing_parent:
            # Link registration to existing parent
            reg.parent_id = existing_parent.id
        else:
            # Create new parent account
            valid, err = validate_password(data.password)
            if valid:
                code, expires = generate_verification_code()
                parent = Parent(
                    email=data.email,
                    password_hash=hash_password(data.password),
                    name=data.parent_name,
                    phone=data.phone,
                    language=data.language,
                    verification_code=code,
                    verification_expires=expires,
                )
                db.add(parent)
                db.flush()
                reg.parent_id = parent.id

                # Send verification email (best-effort)
                try:
                    from services.email import send_verification_email
                    await send_verification_email(parent, code)
                except Exception:
                    pass
        db.commit()

    event_type = "waitlisted" if reg.status == "waitlisted" else "created"
    publish_event("registration", event_type, {
        "registration_id": reg.id,
        "parent_name": reg.parent_name,
        "child_name": reg.child_name,
        "child_age": reg.child_age,
        "phone": reg.phone,
        "email": reg.email,
        "class_name": ct.name_en,
        "block_name": block.name,
        "status": reg.status,
        "language": reg.language,
    })

    # Build schedule summary
    from models import ClassSlot
    slots = (
        db.query(ClassSlot)
        .filter_by(block_id=block.id, class_type_id=ct.id)
        .order_by(ClassSlot.day_of_week, ClassSlot.start_time)
        .all()
    )
    schedule_parts_en = []
    schedule_parts_es = []
    for s in slots:
        t = s.start_time.strftime("%I:%M %p").lstrip("0")
        schedule_parts_en.append(f"{DAY_NAMES_EN[s.day_of_week]} {t}")
        schedule_parts_es.append(f"{DAY_NAMES_ES[s.day_of_week]} {t}")

    schedule_en = ", ".join(schedule_parts_en)
    schedule_es = ", ".join(schedule_parts_es)

    if status == "registered":
        msg_en = f"{data.child_name} has been registered for {ct.name_en}! A confirmation email has been sent to {data.email}."
        msg_es = f"¡{data.child_name} ha sido registrado/a en {ct.name_es}! Se ha enviado un correo de confirmación a {data.email}."
    else:
        waitlist_pos = db.query(Registration).filter(
            Registration.class_type_id == ct.id,
            Registration.block_id == block.id,
            Registration.status == "waitlisted"
        ).count()
        msg_en = f"{ct.name_en} is currently full. {data.child_name} has been added to the waitlist (position #{waitlist_pos}). You will be notified by email if a spot opens up."
        msg_es = f"{ct.name_es} está lleno actualmente. {data.child_name} ha sido añadido/a a la lista de espera (posición #{waitlist_pos}). Se le notificará por correo si se abre un espacio."

    result = {
        "id": reg.id,
        "status": status,
        "child_name": data.child_name,
        "class_name_en": ct.name_en,
        "class_name_es": ct.name_es,
        "block_name": block.name,
        "block_start": format_date_en(block.start_date),
        "block_end": format_date_en(block.end_date),
        "schedule_summary_en": schedule_en,
        "schedule_summary_es": schedule_es,
        "message_en": msg_en,
        "message_es": msg_es,
    }

    # Send emails (non-blocking, don't fail the registration if email fails)
    try:
        await send_registration_email(reg, ct, block, schedule_en, schedule_es)
        await send_registration_notification(reg, ct, block, schedule_en)
    except Exception as e:
        print(f"Email send failed: {e}")

    return result


@router.post("/classes/cancel/{registration_id}")
async def cancel_registration(registration_id: int, db: Session = Depends(get_db)):
    reg = db.query(Registration).filter_by(id=registration_id).first()
    if not reg:
        raise HTTPException(status_code=404, detail="Registration not found")
    if reg.status == "cancelled":
        raise HTTPException(status_code=400, detail="Already cancelled")

    was_registered = reg.status == "registered"
    reg.status = "cancelled"
    db.commit()

    cancelled_ct = db.query(ClassType).filter_by(id=reg.class_type_id).first()
    publish_event("registration", "cancelled", {
        "registration_id": registration_id,
        "child_name": reg.child_name,
        "parent_name": reg.parent_name,
        "class_name": cancelled_ct.name_en if cancelled_ct else "",
    })

    # If they were registered (not waitlisted), promote next waitlisted person
    if was_registered:
        next_waitlisted = (
            db.query(Registration)
            .filter(
                Registration.class_type_id == reg.class_type_id,
                Registration.block_id == reg.block_id,
                Registration.status == "waitlisted"
            )
            .order_by(Registration.created_at)
            .first()
        )
        if next_waitlisted:
            ct = db.query(ClassType).filter_by(id=reg.class_type_id).first()
            block = db.query(Block).filter_by(id=reg.block_id).first()
            next_waitlisted.status = "registered"
            db.commit()
            publish_event("registration", "waitlist_promoted", {
                "registration_id": next_waitlisted.id,
                "child_name": next_waitlisted.child_name,
                "parent_name": next_waitlisted.parent_name,
                "class_name": ct.name_en,
                "block_name": block.name,
            })
            try:
                from services.email import send_waitlist_promotion_email
                await send_waitlist_promotion_email(next_waitlisted, ct, block)
            except Exception as e:
                print(f"Waitlist promotion email failed: {e}")

    return {"status": "cancelled", "id": registration_id}


@router.post("/classes/confirm-waitlist/{registration_id}")
def confirm_waitlist(registration_id: int, db: Session = Depends(get_db)):
    reg = db.query(Registration).filter_by(id=registration_id).first()
    if not reg:
        raise HTTPException(status_code=404, detail="Registration not found")
    if reg.status != "waitlisted":
        raise HTTPException(status_code=400, detail="Registration is not on the waitlist")

    ct = db.query(ClassType).filter_by(id=reg.class_type_id).first()
    block = get_active_block(db)
    registered_count = get_registered_count(db, ct.id, block.id)

    if registered_count >= ct.max_capacity:
        raise HTTPException(status_code=409, detail="Class is still full — spot was taken")

    reg.status = "registered"
    db.commit()

    publish_event("registration", "waitlist_confirmed", {
        "registration_id": registration_id,
        "child_name": reg.child_name,
        "parent_name": reg.parent_name,
        "class_name": ct.name_en,
    })

    return {"status": "registered", "id": registration_id, "child_name": reg.child_name}
