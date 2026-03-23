import uuid
from datetime import time

from Domain.value_objects.day_of_week import DayOfWeek
from infrastructure.database.session import Base
from sqlalchemy import Enum as SQLEnum
from sqlalchemy import ForeignKey, Integer, String, Time
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship


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

    specialty: Mapped["SpecialtyModel"] = relationship(back_populates="doctors")
    schedules: Mapped[list["DoctorScheduleModel"]] = relationship(back_populates="doctor")


class DoctorScheduleModel(Base):
    __tablename__ = "doctor_schedules"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    doctor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("doctors.user_id"), nullable=False)
    day_of_week: Mapped[DayOfWeek] = mapped_column(SQLEnum(DayOfWeek), nullable=False)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    slot_duration_minutes: Mapped[int] = mapped_column(Integer, default=30)

    doctor: Mapped["DoctorModel"] = relationship(back_populates="schedules")
