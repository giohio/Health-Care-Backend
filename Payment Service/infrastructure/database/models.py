import datetime
import uuid

from Domain.value_objects.payment_status import PaymentStatus
from Domain.value_objects.payment_transaction_type import PaymentTransactionType
from healthai_db.base import TimestampMixin, UUIDMixin
from infrastructure.database.session import Base
from sqlalchemy import DateTime
from sqlalchemy import Enum as SQLEnum
from sqlalchemy import Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column


class PaymentModel(Base):
    __tablename__ = "payments"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    appointment_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    patient_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    doctor_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)

    amount: Mapped[int] = mapped_column(Integer, nullable=False)  # in VND
    currency: Mapped[str] = mapped_column(String(3), default="VND", nullable=False)
    status: Mapped[PaymentStatus] = mapped_column(SQLEnum(PaymentStatus), default=PaymentStatus.PENDING, nullable=False)

    vnpay_txn_ref: Mapped[str | None] = mapped_column(String(100), nullable=True, unique=True)
    vnpay_provider_ref: Mapped[str | None] = mapped_column(String(100), nullable=True)
    payment_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    paid_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.datetime.now(datetime.timezone.utc)
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.datetime.now(datetime.timezone.utc),
        onupdate=lambda: datetime.datetime.now(datetime.timezone.utc),
    )

    __table_args__ = (
        Index("idx_payment_appointment", "appointment_id"),
        Index("idx_payment_patient", "patient_id"),
        Index("idx_payment_status", "status"),
        Index("idx_payment_created", "created_at"),
        UniqueConstraint("appointment_id", name="uq_appointment_payment"),
    )


class PaymentTransactionModel(Base):
    __tablename__ = "payment_transactions"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    payment_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    appointment_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    transaction_type: Mapped[PaymentTransactionType] = mapped_column(
        SQLEnum(PaymentTransactionType),
        nullable=False,
    )
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="VND")
    provider_ref: Mapped[str | None] = mapped_column(String(100), nullable=True)
    response_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.datetime.now(datetime.timezone.utc),
    )

    __table_args__ = (
        Index("idx_payment_txn_payment", "payment_id", "created_at"),
        Index("idx_payment_txn_appointment", "appointment_id", "created_at"),
        Index("idx_payment_txn_type", "transaction_type", "created_at"),
    )


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
    published_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
