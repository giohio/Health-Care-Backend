import datetime
import uuid
from typing import Any

from Domain.value_objects.lab_result_status import LabResultStatus
from Domain.value_objects.order_priority import OrderPriority
from Domain.value_objects.test_type import TestType
from infrastructure.database.session import Base
from sqlalchemy import CheckConstraint, DateTime, Float, Index, String, Text
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func


class LabOrderModel(Base):
    __tablename__ = "lab_orders"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    doctor_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    appointment_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    test_name: Mapped[str] = mapped_column(String(255), nullable=False)
    test_type: Mapped[TestType | None] = mapped_column(SQLEnum(TestType), nullable=True)
    department: Mapped[str | None] = mapped_column(String(50), nullable=True)
    instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    priority: Mapped[OrderPriority] = mapped_column(
        SQLEnum(OrderPriority), default=OrderPriority.ROUTINE, nullable=False
    )
    fee: Mapped[int] = mapped_column(default=0, nullable=False, server_default="0")
    payment_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="UNPAID", server_default="UNPAID"
    )
    ordered_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("idx_orders_patient_id", "patient_id"),
        Index("idx_orders_doctor_id", "doctor_id"),
        Index("idx_orders_patient_created", "patient_id", "created_at"),
        Index("idx_orders_appointment_id", "appointment_id"),
    )


class LabResultModel(Base):
    __tablename__ = "lab_results"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    order_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    patient_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    doctor_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)

    # File storage
    file_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_type: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Status lifecycle
    status: Mapped[LabResultStatus] = mapped_column(
        SQLEnum(LabResultStatus), default=LabResultStatus.PENDING, nullable=False
    )

    # Specialist review routing
    reviewer_doctor_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    required_specialty: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Raw manual-entry data — never overwritten by AI; used for retry
    raw_input_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    # AI output
    ai_visual_findings: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    ai_draft_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_draft_citations: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    ai_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    ai_model_versions: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    ai_processed_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Doctor review
    doctor_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    verified_by: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    verified_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Published content
    published_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_findings: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    published_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("idx_results_patient_id", "patient_id"),
        Index("idx_results_status", "status"),
        Index("idx_results_patient_status", "patient_id", "status"),
        Index("idx_results_doctor_id", "doctor_id"),
        Index("idx_results_reviewer_doctor_id", "reviewer_doctor_id"),
        Index("idx_results_required_specialty", "required_specialty"),
        # DB-level constraint: published results must have verified_by and verified_at
        CheckConstraint(
            "status != 'PUBLISHED' OR (verified_by IS NOT NULL AND verified_at IS NOT NULL)",
            name="published_requires_doctor",
        ),
    )


class LabOrderTemplateModel(Base):
    __tablename__ = "lab_order_templates"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    department: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # List of TemplateTestItem dicts stored as JSONB
    test_items: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    creator_type: Mapped[str] = mapped_column(String(20), nullable=False)  # SYSTEM | PERSONAL
    creator_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        Index("idx_templates_creator_type_dept", "creator_type", "department"),
        Index("idx_templates_creator_id", "creator_id"),
    )


class AppointmentLabSummaryModel(Base):
    __tablename__ = "appointment_lab_summaries"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    appointment_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, unique=True)
    patient_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")
    ai_holistic_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    total_results: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    doctor_conclusion: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    reviewed_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("idx_appt_summary_patient_id", "patient_id"),
        Index("idx_appt_summary_status", "status"),
    )


class AiAuditLogModel(Base):
    __tablename__ = "ai_audit_log"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    result_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True, index=True)
    patient_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    step: Mapped[str | None] = mapped_column(String(50), nullable=True)
    input_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    output_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(nullable=True)
    success: Mapped[bool | None] = mapped_column(nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
