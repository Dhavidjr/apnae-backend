"""
Database models.

User            -> a registered account (owns one or more devices)
Device          -> a piece of hardware registered by a user (identified by device_id)
SensorReading   -> a single telemetry sample sent by a device
AIReview        -> a stored result of an (placeholder) apnoea prediction run
"""
import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from app.database import Base


def utcnow():
    return datetime.datetime.utcnow()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(64), unique=True, index=True, nullable=False)
    email = Column(String(128), unique=True, index=True, nullable=False)
    full_name = Column(String(128), nullable=True)
    hashed_password = Column(String(256), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)

    devices = relationship(
        "Device", back_populates="owner", cascade="all, delete-orphan"
    )
    ai_reviews = relationship(
        "AIReview", back_populates="user", cascade="all, delete-orphan"
    )


class Device(Base):
    __tablename__ = "devices"

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(String(64), unique=True, index=True, nullable=False)
    device_secret = Column(String(128), nullable=False)
    name = Column(String(128), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    last_seen_at = Column(DateTime, nullable=True)

    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    owner = relationship("User", back_populates="devices")
    readings = relationship(
        "SensorReading", back_populates="device", cascade="all, delete-orphan"
    )
    ai_reviews = relationship(
        "AIReview", back_populates="device", cascade="all, delete-orphan"
    )


class SensorReading(Base):
    __tablename__ = "sensor_readings"

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(Integer, ForeignKey("devices.id"), nullable=False, index=True)

    body_temperature = Column(Float, nullable=False)
    heart_rate = Column(Float, nullable=False)
    spo2 = Column(Float, nullable=False)
    heart_beat_height = Column(Float, nullable=False)  # accelerometer-derived value

    recorded_at = Column(DateTime, default=utcnow, nullable=False, index=True)

    device = relationship("Device", back_populates="readings")


class AIReview(Base):
    __tablename__ = "ai_reviews"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    device_id = Column(Integer, ForeignKey("devices.id"), nullable=False)

    created_at = Column(DateTime, default=utcnow, nullable=False)
    range_start = Column(DateTime, nullable=True)
    range_end = Column(DateTime, nullable=True)

    samples_analyzed = Column(Integer, default=0, nullable=False)
    apnea_detected = Column(Boolean, default=False, nullable=False)
    risk_score = Column(Float, default=0.0, nullable=False)
    confidence = Column(Float, default=0.0, nullable=False)
    summary = Column(Text, nullable=True)
    model_version = Column(String(64), default="placeholder-v0", nullable=False)
    details = Column(JSON, nullable=True)

    user = relationship("User", back_populates="ai_reviews")
    device = relationship("Device", back_populates="ai_reviews")
