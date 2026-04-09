from pydantic import BaseModel, EmailStr
from datetime import date, time
from typing import Optional


# --- Blocks ---

class BlockOut(BaseModel):
    id: int
    name: str
    start_date: date
    end_date: date
    status: str

    class Config:
        from_attributes = True


# --- Class Types ---

class ClassTypeOut(BaseModel):
    id: int
    key: str
    name_en: str
    name_es: str
    age_range_text_en: str
    age_range_text_es: str
    min_age: float
    max_age: float
    max_capacity: int
    description_en: str
    description_es: str

    class Config:
        from_attributes = True


# --- Schedule ---

class ClassSlotOut(BaseModel):
    id: int
    day_of_week: int
    start_time: str  # HH:MM format
    end_time: str
    class_type: ClassTypeOut
    registered_count: int
    spots_remaining: int
    is_full: bool

    class Config:
        from_attributes = True


class ScheduleOut(BaseModel):
    block: BlockOut
    slots: list[ClassSlotOut]


# --- Registration ---

class RegistrationIn(BaseModel):
    class_type_id: int
    parent_name: str
    child_name: str
    child_age: float
    phone: str
    email: str
    emergency_contact: str
    language: str = "en"


class RegistrationOut(BaseModel):
    id: int
    status: str  # "registered" or "waitlisted"
    child_name: str
    class_name_en: str
    class_name_es: str
    block_name: str
    block_start: date
    block_end: date
    schedule_summary_en: str
    schedule_summary_es: str
    message_en: str
    message_es: str


# --- Rental ---

class AvailableHour(BaseModel):
    hour: int  # 0-23
    label: str  # e.g. "6:00 PM"
    available: bool
    reason: Optional[str] = None  # "class" or "booked" if unavailable


class RentalAvailabilityOut(BaseModel):
    date: date
    day_name_en: str
    day_name_es: str
    hours: list[AvailableHour]
    studio_open: int
    studio_close: int


class RentalBookingIn(BaseModel):
    date: date
    start_hour: int  # 0-23
    end_hour: int    # 0-23 (exclusive)
    renter_name: str
    phone: str
    email: str
    purpose: str
    language: str = "en"


class RentalBookingOut(BaseModel):
    id: int
    date: date
    start_time: str
    end_time: str
    hours: int
    rate_per_hour: float
    total_price: float
    renter_name: str
    status: str
    message_en: str
    message_es: str
