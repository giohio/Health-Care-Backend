from datetime import datetime

from Domain.entities.user import UserRole
from sqlalchemy import Boolean, DateTime
from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, String
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

    role: Mapped[str] = mapped_column(
        SAEnum(UserRole, name="userrole", values_callable=lambda obj: [e.value for e in obj]),
        nullable=False,
        default=UserRole.PATIENT,
    )

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_email_verified: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
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
