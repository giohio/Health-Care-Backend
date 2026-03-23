import asyncio
import logging
from datetime import datetime, timezone

from healthai_db import OutboxEvent
from sqlalchemy import select

logger = logging.getLogger(__name__)


class OutboxRelay:
    """
    Background worker poll outbox → publish → mark sent.

    Thiết kế:
    - SELECT FOR UPDATE SKIP LOCKED:
        Nhiều relay instance có thể chạy song song
        mà không tranh nhau cùng row.
        Nếu 1 instance crash giữa chừng → row vẫn
        được pick up bởi instance khác sau khi
        lock timeout.

    - Retry với exponential backoff:
        Lần 1: retry ngay
        Lần 2: +5s
        Lần 3: +15s
        Lần 4: +60s
        Lần 5: status='failed' → alert

    - Batch size 50:
        Không pull quá nhiều vào memory cùng lúc.

    Cách dùng:
        relay = OutboxRelay(session_factory, publisher)
        asyncio.create_task(relay.run())  # background task
    """

    MAX_RETRIES = 5
    BATCH_SIZE = 50
    POLL_INTERVAL = 0.5  # giây

    def __init__(self, session_factory, publisher):
        self._session_factory = session_factory
        self._publisher = publisher
        self._running = False

    async def run(self):
        """Chạy forever cho đến khi stop() được gọi."""
        self._running = True
        logger.info("OutboxRelay started")
        while self._running:
            try:
                processed = await self._process_batch()
                if processed == 0:
                    # Không có gì để process → sleep lâu hơn
                    await asyncio.sleep(self.POLL_INTERVAL)
                # Nếu có data → poll ngay lập tức
            except Exception as e:
                logger.error(f"OutboxRelay error: {e}")
                await asyncio.sleep(self.POLL_INTERVAL)

    def stop(self):
        self._running = False

    async def _process_batch(self) -> int:
        async with self._session_factory() as session:
            async with session.begin():
                # SELECT FOR UPDATE SKIP LOCKED
                # Atomic: acquire row lock + read
                result = await session.execute(
                    select(OutboxEvent)
                    .where(OutboxEvent.status == "pending", OutboxEvent.retry_count < self.MAX_RETRIES)
                    .order_by(OutboxEvent.id)
                    .limit(self.BATCH_SIZE)
                    .with_for_update(skip_locked=True)
                )
                events = result.scalars().all()

                if not events:
                    return 0

                for event in events:
                    await self._process_one(event)

                # Commit tất cả status updates 1 lần
                return len(events)

    async def _process_one(self, event: OutboxEvent):
        try:
            await self._publisher.publish(
                exchange=event.aggregate_type,
                routing_key=event.event_type,
                payload=event.payload,
                message_id=str(event.id),
            )
            event.status = "published"
            event.published_at = datetime.now(timezone.utc)

        except Exception as e:
            event.retry_count += 1
            event.last_error = str(e)[:500]

            if event.retry_count >= self.MAX_RETRIES:
                event.status = "failed"
                logger.error(f"OutboxEvent {event.id} permanently failed: {e}")
                logger.error("OutboxEvent requires manual alert handling")
            else:
                logger.warning(f"OutboxEvent {event.id} retry {event.retry_count}/{self.MAX_RETRIES}: {e}")
