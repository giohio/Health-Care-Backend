import datetime
import uuid

from Domain.value_objects.appointment_status import AppointmentStatus
from Domain.value_objects.payment_status import PaymentStatus
from infrastructure.database.session import Base
from sqlalchemy import Boolean, Date, DateTime
from sqlalchemy import Enum as SQLEnum
from sqlalchemy import Index, Integer, String, Text, Time, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column


class AppointmentModel(Base):
    __tablename__ = "appointments"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    patient_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    doctor_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    specialty_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)

    appointment_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    start_time: Mapped[datetime.time] = mapped_column(Time, nullable=False)
    end_time: Mapped[datetime.time] = mapped_column(Time, nullable=False)
    appointment_type: Mapped[str] = mapped_column(String(50), default="general", nullable=False)
    chief_complaint: Mapped[str | None] = mapped_column(Text, nullable=True)
    note_for_doctor: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[AppointmentStatus] = mapped_column(
        SQLEnum(AppointmentStatus), default=AppointmentStatus.PENDING, nullable=False
    )
    payment_status: Mapped[PaymentStatus] = mapped_column(
        SQLEnum(PaymentStatus), default=PaymentStatus.UNPAID, nullable=False
    )
    confirmed_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_by: Mapped[str | None] = mapped_column(String(20), nullable=True)
    cancelled_by_user_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    cancel_reason: Mapped[str | None] = mapped_column(String(100), nullable=True)
    queue_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reminder_24h_sent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    reminder_1h_sent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Indexes for performance and uniqueness constraints
    __table_args__ = (
        Index("idx_doctor_date_time", "doctor_id", "appointment_date", "start_time"),
        Index(
            "idx_doctor_slot_active",
            "doctor_id",
            "appointment_date",
            "start_time",
            postgresql_where=("status IN ('pending_payment','pending','confirmed')"),
        ),
        Index("idx_doctor_queue", "doctor_id", "appointment_date", "status"),
        Index("idx_patient_history", "patient_id", "appointment_date"),
    )


class AppointmentTypeConfigModel(Base):
    __tablename__ = "appointment_type_configs"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    specialty_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    type_name: Mapped[str] = mapped_column(String(50), nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    buffer_minutes: Mapped[int] = mapped_column(Integer, default=5, nullable=False)

    __table_args__ = (UniqueConstraint("specialty_id", "type_name", name="uq_specialty_type"),)
