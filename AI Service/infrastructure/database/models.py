import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Enum as SQLEnum, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from Domain.enums import TriageSessionStatus
from infrastructure.database.session import Base, TimestampMixin


class TriageSessionModel(Base, TimestampMixin):
    __tablename__ = "triage_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    patient_id: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[TriageSessionStatus] = mapped_column(
        SQLEnum(TriageSessionStatus), nullable=False, default=TriageSessionStatus.ACTIVE
    )
    messages: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    suggested_department: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    urgency_level:        Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    doctor_id:            Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    final_department:     Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    doctor_notes:         Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    completed_at:         Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Tracks the appointment_id created after AI-guided booking
    appointment_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    # Stores the patient's pending booking request waiting for doctor confirmation
    pending_booking: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    __table_args__ = (
        Index("idx_triage_patient_created", "patient_id", "created_at"),
        Index("idx_triage_status_created", "status", "created_at"),
    )


class ChatSessionModel(Base, TimestampMixin):
    """Persisted multi-turn chat sessions for lab_chat and clinical_assist."""

    __tablename__ = "chat_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id:      Mapped[str] = mapped_column(String(64), nullable=False)
    user_role:    Mapped[str] = mapped_column(String(32), nullable=False)
    session_type: Mapped[str] = mapped_column(String(32), nullable=False)
    messages:     Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    patient_id:   Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    department:   Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        Index("idx_chat_user_created", "user_id", "created_at"),
        Index("idx_chat_type_created", "session_type", "created_at"),
    )
