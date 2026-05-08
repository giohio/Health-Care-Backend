import datetime
import uuid

from Domain.value_objects.diagnosis_status import DiagnosisStatus
from Domain.value_objects.medication_status import MedicationStatus
from Domain.value_objects.note_type import NoteType
from Domain.value_objects.record_source import RecordSource
from Domain.value_objects.severity import Severity
from infrastructure.database.session import Base
from sqlalchemy import Boolean, Date, DateTime, Index, String, Text
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func


class DiagnosisModel(Base):
    __tablename__ = "diagnoses"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    doctor_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    appointment_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True
    )
    icd10_code: Mapped[str | None] = mapped_column(String(10), nullable=True)
    diagnosis_name: Mapped[str] = mapped_column(String(255), nullable=False)
    diagnosis_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    severity: Mapped[Severity | None] = mapped_column(SQLEnum(Severity), nullable=True)
    status: Mapped[DiagnosisStatus] = mapped_column(
        SQLEnum(DiagnosisStatus),
        default=DiagnosisStatus.ACTIVE,
        nullable=False,
    )
    diagnosed_at: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    resolved_at: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    source: Mapped[RecordSource] = mapped_column(
        SQLEnum(RecordSource),
        default=RecordSource.DOCTOR,
        nullable=False,
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("idx_diagnoses_patient_id", "patient_id"),
        Index("idx_diagnoses_patient_status", "patient_id", "status"),
        Index("idx_diagnoses_patient_date", "patient_id", "diagnosed_at"),
    )


class MedicationModel(Base):
    __tablename__ = "medications"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    doctor_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    appointment_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True
    )
    drug_name: Mapped[str] = mapped_column(String(255), nullable=False)
    dosage: Mapped[str | None] = mapped_column(String(100), nullable=True)
    frequency: Mapped[str | None] = mapped_column(String(100), nullable=True)
    route: Mapped[str | None] = mapped_column(String(50), nullable=True)
    start_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    end_date: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    status: Mapped[MedicationStatus] = mapped_column(
        SQLEnum(MedicationStatus),
        default=MedicationStatus.ACTIVE,
        nullable=False,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("idx_medications_patient_id", "patient_id"),
        Index("idx_medications_patient_status", "patient_id", "status"),
    )


class ClinicalNoteModel(Base):
    __tablename__ = "clinical_notes"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    doctor_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    appointment_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True
    )
    note_type: Mapped[NoteType | None] = mapped_column(SQLEnum(NoteType), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    is_ai_generated: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("idx_notes_patient_id", "patient_id"),
        Index("idx_notes_patient_created", "patient_id", "created_at"),
        Index("idx_notes_appointment_id", "appointment_id"),
    )


class VaccinationModel(Base):
    __tablename__ = "vaccinations"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    vaccine_name: Mapped[str] = mapped_column(String(255), nullable=False)
    date_administered: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    next_due_date: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("idx_vaccinations_patient_id", "patient_id"),
        Index("idx_vaccinations_patient_date", "patient_id", "date_administered"),
    )
