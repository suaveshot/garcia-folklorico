from sqlalchemy import (
    Column, Integer, String, Date, Time, Float, DateTime, ForeignKey,
    create_engine, event
)
from sqlalchemy.orm import relationship, declarative_base, sessionmaker
from datetime import datetime
from config import DATABASE_URL

Base = declarative_base()


class Block(Base):
    __tablename__ = "blocks"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    status = Column(String, nullable=False, default="active")  # active, upcoming, past

    class_slots = relationship("ClassSlot", back_populates="block")


class ClassType(Base):
    __tablename__ = "class_types"

    id = Column(Integer, primary_key=True)
    key = Column(String, unique=True, nullable=False)  # e.g. "semillas"
    name_en = Column(String, nullable=False)
    name_es = Column(String, nullable=False)
    age_range_text_en = Column(String, nullable=False)
    age_range_text_es = Column(String, nullable=False)
    min_age = Column(Float, nullable=False)
    max_age = Column(Float, nullable=False)
    max_capacity = Column(Integer, nullable=False)
    description_en = Column(String, default="")
    description_es = Column(String, default="")

    class_slots = relationship("ClassSlot", back_populates="class_type")


class ClassSlot(Base):
    __tablename__ = "class_slots"

    id = Column(Integer, primary_key=True)
    block_id = Column(Integer, ForeignKey("blocks.id"), nullable=False)
    class_type_id = Column(Integer, ForeignKey("class_types.id"), nullable=False)
    day_of_week = Column(Integer, nullable=False)  # 0=Monday .. 6=Sunday
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)

    block = relationship("Block", back_populates="class_slots")
    class_type = relationship("ClassType", back_populates="class_slots")


class Parent(Base):
    __tablename__ = "parents"

    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    name = Column(String, nullable=False)
    phone = Column(String, nullable=False, default="")
    language = Column(String, nullable=False, default="en")
    email_verified = Column(Integer, nullable=False, default=0)  # SQLite has no bool
    verification_code = Column(String, nullable=True)
    verification_expires = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    registrations = relationship("Registration", back_populates="parent")
    rental_bookings = relationship("RentalBooking", back_populates="parent")


class PasswordReset(Base):
    __tablename__ = "password_resets"

    id = Column(Integer, primary_key=True)
    parent_id = Column(Integer, ForeignKey("parents.id"), nullable=False)
    token_hash = Column(String, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    used = Column(Integer, nullable=False, default=0)  # SQLite bool
    created_at = Column(DateTime, default=datetime.utcnow)

    parent = relationship("Parent")


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id = Column(Integer, primary_key=True)
    parent_id = Column(Integer, ForeignKey("parents.id"), nullable=False)
    token_hash = Column(String, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    revoked = Column(Integer, nullable=False, default=0)  # SQLite bool
    created_at = Column(DateTime, default=datetime.utcnow)

    parent = relationship("Parent")


class Registration(Base):
    __tablename__ = "registrations"

    id = Column(Integer, primary_key=True)
    class_type_id = Column(Integer, ForeignKey("class_types.id"), nullable=False)
    block_id = Column(Integer, ForeignKey("blocks.id"), nullable=False)
    parent_name = Column(String, nullable=False)
    child_name = Column(String, nullable=False)
    child_age = Column(Float, nullable=False)
    phone = Column(String, nullable=False)
    email = Column(String, nullable=False)
    emergency_contact = Column(String, nullable=False)
    status = Column(String, nullable=False, default="registered")  # registered, waitlisted, cancelled
    language = Column(String, nullable=False, default="en")
    created_at = Column(DateTime, default=datetime.utcnow)
    parent_id = Column(Integer, ForeignKey("parents.id"), nullable=True)
    payment_status = Column(String, nullable=False, default="unpaid")  # unpaid/paid/partial/refunded
    payment_method = Column(String, nullable=True)  # card/cash/zelle/venmo/check
    stripe_session_id = Column(String, nullable=True)

    class_type = relationship("ClassType")
    block = relationship("Block")
    parent = relationship("Parent", back_populates="registrations")


class RentalBooking(Base):
    __tablename__ = "rental_bookings"

    id = Column(Integer, primary_key=True)
    date = Column(Date, nullable=False)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    hours = Column(Integer, nullable=False)
    total_price = Column(Float, nullable=False)
    renter_name = Column(String, nullable=False)
    phone = Column(String, nullable=False)
    email = Column(String, nullable=False)
    purpose = Column(String, nullable=False)
    status = Column(String, nullable=False, default="confirmed")  # confirmed, cancelled
    language = Column(String, nullable=False, default="en")
    created_at = Column(DateTime, default=datetime.utcnow)
    parent_id = Column(Integer, ForeignKey("parents.id"), nullable=True)
    payment_status = Column(String, nullable=False, default="unpaid")
    payment_method = Column(String, nullable=True)
    stripe_session_id = Column(String, nullable=True)

    parent = relationship("Parent", back_populates="rental_bookings")


# Database setup
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})


@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


SessionLocal = sessionmaker(bind=engine)


def init_db():
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
