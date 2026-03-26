import uuid
from datetime import date, datetime, time

from Domain.value_objects.day_of_week import DayOfWeek
from healthai_db.base import TimestampMixin, UUIDMixin
from infrastructure.database.session import Base
from sqlalchemy import DateTime
from sqlalchemy import Enum as SQLEnum
from sqlalchemy import ForeignKey, Index, Integer, String, Text, Time
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

DOCTOR_ID_FK = "doctors.user_id"


class SpecialtyModel(Base):
    __tablename__ = "specialties"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))

    doctors: Mapped[list["DoctorModel"]] = relationship(back_populates="specialty")


class DoctorModel(Base):
    __tablename__ = "doctors"

    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    specialty_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("specialties.id"), nullable=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str | None] = mapped_column(String(50))
    experience_years: Mapped[int] = mapped_column(Integer, default=0)
    auto_confirm: Mapped[bool] = mapped_column(default=True, nullable=False)
    confirmation_timeout_minutes: Mapped[int] = mapped_column(Integer, default=15, nullable=False)
    average_rating: Mapped[float] = mapped_column(default=0.0, server_default="0", nullable=False)
    rating_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)

    specialty: Mapped["SpecialtyModel"] = relationship(back_populates="doctors")
    schedules: Mapped[list["DoctorScheduleModel"]] = relationship(back_populates="doctor")


class DoctorScheduleModel(Base):
    __tablename__ = "doctor_schedules"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    doctor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(DOCTOR_ID_FK), nullable=False)
    day_of_week: Mapped[DayOfWeek] = mapped_column(SQLEnum(DayOfWeek), nullable=False)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    slot_duration_minutes: Mapped[int] = mapped_column(Integer, default=30)

    doctor: Mapped["DoctorModel"] = relationship(back_populates="schedules")


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


class DoctorAvailabilityModel(Base):
    __tablename__ = "doctor_availability"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    doctor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(DOCTOR_ID_FK), nullable=False)
    day_of_week: Mapped[int] = mapped_column(Integer, nullable=False)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    break_start: Mapped[time | None] = mapped_column(Time, nullable=True)
    break_end: Mapped[time | None] = mapped_column(Time, nullable=True)
    max_patients: Mapped[int] = mapped_column(Integer, default=20)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


class DoctorDayOffModel(Base):
    __tablename__ = "doctor_day_off"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    doctor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(DOCTOR_ID_FK), nullable=False)
    off_date: Mapped[date] = mapped_column(nullable=False)
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class DoctorServiceOfferingModel(Base):
    __tablename__ = "doctor_service_offerings"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    doctor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(DOCTOR_ID_FK), nullable=False)
    service_name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    fee: Mapped[float] = mapped_column(nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


class DoctorRatingModel(Base):
    __tablename__ = "doctor_rating"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    doctor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(DOCTOR_ID_FK), nullable=False)
    patient_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
