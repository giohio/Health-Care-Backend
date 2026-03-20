from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy import String, Integer, Text, DateTime, Index
from uuid_extension import uuid7, UUID7
from datetime import datetime
from typing import Optional, Any
from healthai_db.base import Base, UUIDMixin, TimestampMixin


class OutboxEvent(Base, UUIDMixin, TimestampMixin):
    """
    Transactional outbox table.
    Mỗi service có 1 bảng này trong DB của mình.
    Relay sẽ poll và publish lên RabbitMQ.

    QUAN TRỌNG: Insert outbox_event CÙNG transaction
    với entity chính để đảm bảo atomicity.
    Không bao giờ insert outbox sau khi commit entity.
    """
    __tablename__ = 'outbox_events'

    __table_args__ = (
        # Index cho relay poll — chỉ query pending
        Index(
            'idx_outbox_pending',
            'status', 'created_at',
            postgresql_where="status = 'pending'"
        ),
        # Index để retry failed events
        Index(
            'idx_outbox_retry',
            'status', 'retry_count',
            postgresql_where="status = 'failed'"
        ),
    )

    # Loại entity phát ra event
    aggregate_id: Mapped[UUID7] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=False,
        index=True
    )
    aggregate_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False
    )
    # Tên event, dùng làm routing_key trong RabbitMQ
    event_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False
    )
    # JSON payload đầy đủ
    payload: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(20),
        default='pending',
        nullable=False
    )
    # Số lần đã retry publish
    retry_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False
    )
    last_error: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True
    )
    published_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )


class OutboxWriter:
    """
    Helper để insert outbox event vào session.
    Dùng cùng session với entity để đảm bảo atomicity.

    Usage:
        async with session.begin():
            session.add(appointment)
            await OutboxWriter.write(
                session,
                aggregate_id=appointment.id,
                aggregate_type='appointment_events',
                event_type='appointment.created',
                payload={'appointment_id': str(appointment.id)}
            )
        # Commit một lần duy nhất — cả appointment lẫn outbox
    """
    @staticmethod
    async def write(
        session,
        aggregate_id: Any,
        aggregate_type: str,
        event_type: str,
        payload: dict
    ) -> OutboxEvent:
        """Write single outbox event."""
        event = OutboxEvent(
            aggregate_id=aggregate_id,
            aggregate_type=aggregate_type,
            event_type=event_type,
            payload=payload
        )
        session.add(event)
        return event

    @staticmethod
    async def write_many(
        session,
        events: list[dict]
    ) -> list[OutboxEvent]:
        """
        Bulk insert nhiều events trong 1 transaction.
        Dùng khi 1 action cần phát nhiều events.
        """
        objs = [OutboxEvent(**e) for e in events]
        session.add_all(objs)
        return objs
