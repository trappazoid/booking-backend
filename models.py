from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, Enum, Float
from sqlalchemy.orm import relationship
from datetime import datetime
import enum

# Import database components from database.py
from database import Base, SessionLocal, engine, get_db


class SeatStatus(enum.Enum):
    available = "available"
    cart = "cart"
    booked = "booked"


class SeatType(enum.Enum):
    sitting = "sitting"
    vip = "vip"
    standing = "standing"


class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    password = Column(String, nullable=False)  # In production, use hashed passwords
    role = Column(String, default="user")  # "user" or "admin"
    created_at = Column(DateTime, default=datetime.utcnow)
    
    bookings = relationship("Booking", back_populates="user")


class Event(Base):
    __tablename__ = "events"
    
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    description = Column(Text)
    date = Column(DateTime, nullable=False)
    poster_url = Column(String)  # Path to uploaded poster image
    venue_id = Column(Integer, ForeignKey("venues.id"))
    created_at = Column(DateTime, default=datetime.utcnow)
    
    venue = relationship("Venue", back_populates="events")
    seats = relationship("Seat", back_populates="event")


class Venue(Base):
    __tablename__ = "venues"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    schematic_url = Column(String)  # Path to uploaded venue schematic
    schema_json = Column(Text)  # JSON string containing seat zones configuration
    created_at = Column(DateTime, default=datetime.utcnow)
    
    events = relationship("Event", back_populates="venue")


class Seat(Base):
    __tablename__ = "seats"
    
    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(Integer, ForeignKey("events.id"), nullable=False)
    zone_name = Column(String, nullable=False)  # e.g., "VIP Center"
    seat_type = Column(Enum(SeatType), nullable=False)
    row_label = Column(String, nullable=False)  # e.g., "A", "Sector 1"
    seat_number = Column(Integer, nullable=False)
    position_x = Column(Float)  # Canvas position for rendering - CHANGED to Float
    position_y = Column(Float)  # Canvas position for rendering - CHANGED to Float
    price = Column(Integer, default=0)  # Price in cents or basic currency unit
    status = Column(Enum(SeatStatus), default=SeatStatus.available)
    locked_by = Column(Integer, ForeignKey("users.id"), nullable=True)  # User who locked it
    locked_at = Column(DateTime, nullable=True)
    
    event = relationship("Event", back_populates="seats")
    bookings = relationship("Booking", back_populates="seat")


class Booking(Base):
    __tablename__ = "bookings"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    seat_id = Column(Integer, ForeignKey("seats.id"), nullable=False)
    booking_time = Column(DateTime, default=datetime.utcnow)
    payment_code = Column(String)  # The 4-digit code used for mock payment
    
    user = relationship("User", back_populates="bookings")
    seat = relationship("Seat", back_populates="bookings")


# Create all tables
def init_db():
    """Initialize database by creating all tables."""
    Base.metadata.create_all(bind=engine)
