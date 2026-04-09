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

    class_type = relationship("ClassType")
    block = relationship("Block")


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
