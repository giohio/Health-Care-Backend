from datetime import date, datetime
from typing import Any

from Domain.entities.patient_health_background import BloodType
from Domain.entities.patient_profile import Gender
from sqlalchemy import JSON, Date, DateTime, Enum, Float, ForeignKey, Integer, String, Text
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
