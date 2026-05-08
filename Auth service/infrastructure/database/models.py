import uuid
from datetime import datetime, time

from Domain.entities.user import UserRole
from healthai_db.base import TimestampMixin, UUIDMixin
from sqlalchemy import Boolean, DateTime
from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Index, Integer, String, Text, Time
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from uuid_extension import UUID7, uuid7


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[UUID7] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)

    email: Mapped[str] = mapped_column(String(255), nullable=True, unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=True)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    role: Mapped[str] = mapped_column(
        SAEnum(UserRole, name="userrole", values_callable=lambda obj: [e.value for e in obj]),
        nullable=False,
        default=UserRole.PATIENT,
    )

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_email_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_profile_completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[UUID7] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)

    token_value: Mapped[str] = mapped_column(String(512), nullable=False, unique=True, index=True)

    user_id: Mapped[UUID7] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    is_revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    replaced_by_token_id: Mapped[UUID7 | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    user: Mapped["User"] = relationship("User", backref="refresh_tokens")


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


class SystemConfig(Base):
    """Single-row table holding clinic-wide configuration.

    Only one row is expected (`id = 1`). The repository uses upsert semantics.
    """

    __tablename__ = "system_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    clinic_name: Mapped[str] = mapped_column(String(255), default="HealthAI Clinic", nullable=False)
    maintenance_mode: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    default_slot_duration_minutes: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    max_appointments_per_day: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    support_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    working_hours_start: Mapped[time] = mapped_column(Time, default=time(7, 0), nullable=False)
    working_hours_end: Mapped[time] = mapped_column(Time, default=time(18, 0), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now, nullable=False
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)


class SystemSettings(Base):
    """Single-row table holding UI/operational settings (notifications, security, etc.)."""

    __tablename__ = "system_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    notification_settings: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    security_settings: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now, nullable=False
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
