import uuid
from datetime import date, datetime
from typing import Any

from Domain.entities.patient_health_background import BloodType
from Domain.entities.patient_profile import Gender
from healthai_db.base import TimestampMixin, UUIDMixin
from sqlalchemy import JSON, Date, DateTime, Enum, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from uuid_extension import UUID7


class Base(DeclarativeBase):
    pass


class PatientProfileModel(Base):
    __tablename__ = "patient_profiles"

    id: Mapped[UUID7] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    user_id: Mapped[UUID7] = mapped_column(PGUUID(as_uuid=True), unique=True, index=True, nullable=False)

    full_name: Mapped[str | None] = mapped_column(String(255))
    date_of_birth: Mapped[date | None] = mapped_column(Date)
    gender: Mapped[Gender | None] = mapped_column(Enum(Gender))
    phone_number: Mapped[str | None] = mapped_column(String(20))
    address: Mapped[str | None] = mapped_column(Text)
    avatar_url: Mapped[str | None] = mapped_column(String(500))

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    # Relationship to health background (1-1)
    health_background: Mapped["PatientHealthBackgroundModel"] = relationship(
        back_populates="profile", uselist=False, cascade="all, delete-orphan"
    )


class PatientHealthBackgroundModel(Base):
    __tablename__ = "patient_health_backgrounds"

    patient_id: Mapped[UUID7] = mapped_column(PGUUID(as_uuid=True), ForeignKey("patient_profiles.id"), primary_key=True)

    blood_type: Mapped[BloodType | None] = mapped_column(Enum(BloodType))
    height_cm: Mapped[int | None] = mapped_column(Integer)
    weight_kg: Mapped[float | None] = mapped_column(Float)
    allergies: Mapped[Any | None] = mapped_column(JSON)
    chronic_conditions: Mapped[Any | None] = mapped_column(JSON)

    profile: Mapped["PatientProfileModel"] = relationship(back_populates="health_background")


class OutboxEventModel(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "outbox_events"

    __table_args__ = (
        Index("idx_outbox_pending", "status", "created_at", postgresql_where="status = 'pending'"),
        Index("idx_outbox_retry", "status", "retry_count", postgresql_where="status = 'failed'"),
    )

    aggregate_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    aggregate_type: Mapped[str] = mapped_column(String(50), nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PatientVitalsModel(Base):
    __tablename__ = "patient_vitals"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    patient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("patient_profiles.id"), nullable=False)
    recorded_by: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    height_cm: Mapped[float | None] = mapped_column(nullable=True)
    weight_kg: Mapped[float | None] = mapped_column(nullable=True)
    blood_pressure_systolic: Mapped[int | None] = mapped_column(nullable=True)
    blood_pressure_diastolic: Mapped[int | None] = mapped_column(nullable=True)
    heart_rate: Mapped[int | None] = mapped_column(nullable=True)
    temperature_celsius: Mapped[float | None] = mapped_column(nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
