from sqlalchemy import String, Date, Time, Enum as SQLEnum, Index
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from infrastructure.database.session import Base
from Domain.value_objects.appointment_status import AppointmentStatus
from Domain.value_objects.payment_status import PaymentStatus
import uuid
import datetime

class AppointmentModel(Base):
    __tablename__ = "appointments"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    patient_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    doctor_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    specialty_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    
    appointment_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    start_time: Mapped[datetime.time] = mapped_column(Time, nullable=False)
    end_time: Mapped[datetime.time] = mapped_column(Time, nullable=False)
    
    status: Mapped[AppointmentStatus] = mapped_column(
        SQLEnum(AppointmentStatus), 
        default=AppointmentStatus.PENDING, 
        nullable=False
    )
    payment_status: Mapped[PaymentStatus] = mapped_column(
        SQLEnum(PaymentStatus),
        default=PaymentStatus.UNPAID,
        nullable=False
    )

    # Indexes for performance and uniqueness constraints
    __table_args__ = (
        Index("idx_doctor_date_time", "doctor_id", "appointment_date", "start_time"),
    )
