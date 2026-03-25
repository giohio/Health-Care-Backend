from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from uuid_extension import uuid7


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""


class UUIDMixin:
    """
    Primary key dùng UUID7.
    UUID7 là time-ordered — tốt hơn UUID4 cho B-tree index.
    Thứ tự insert = thứ tự thời gian.
    """

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=lambda: UUID(str(uuid7())),
    )


class TimestampMixin:
    """
    Auto-managed created_at và updated_at.
    server_default đảm bảo DB set nếu app quên.
    """

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), onupdate=func.now(), nullable=True)


class SoftDeleteMixin:
    """
    Không xóa thật — chỉ đánh dấu.
    Mọi query cần filter is_deleted=False.
    """

    is_deleted: Mapped[bool] = mapped_column(default=False, nullable=False, index=True)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    def soft_delete(self):
        """Mark entity as deleted."""
        self.is_deleted = True
        self.deleted_at = datetime.now()
