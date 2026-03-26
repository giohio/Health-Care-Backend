import logging
from abc import ABC
from datetime import datetime
from typing import Optional
from uuid import UUID

from healthai_db import Base, TimestampMixin, UUIDMixin
from sqlalchemy import DateTime, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column
from uuid_extension import uuid7

logger = logging.getLogger(__name__)


class SagaState(Base, UUIDMixin, TimestampMixin):
    """
    Persist saga state để recovery khi crash.
    Mỗi service có bảng này trong DB của mình.
    """

    __tablename__ = "saga_states"

    # Use stdlib UUID for DB binding compatibility with asyncpg.
    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=lambda: UUID(str(uuid7())))

    saga_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), default="running", nullable=False)
    # running | completed | compensating | failed
    current_step: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    completed_steps: Mapped[list] = mapped_column(JSONB, default=list)
    compensated_steps: Mapped[list] = mapped_column(JSONB, default=list)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    failed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class SagaFailedError(Exception):
    def __init__(self, message: str, saga_id: str = None):
        super().__init__(message)
        self.saga_id = saga_id


class SagaOrchestrator(ABC):
    """
    Base orchestrator cho distributed sagas.

    Cách dùng:
        class BookAppointmentSaga(SagaOrchestrator):
            SAGA_TYPE = 'book_appointment'

            STEPS = [
                'acquire_lock',
                'create_appointment',
                'publish_event',
            ]

            COMPENSATIONS = {
                'create_appointment': 'cancel_appointment',
                'acquire_lock':       'release_lock',
                # publish_event không compensate được
                # → publish compensation event thay thế
            }

            async def execute_acquire_lock(self, ctx):
                token = await self.cache.lock.acquire(
                    f"slot:{ctx['doctor_id']}:{ctx['date']}"
                )
                if not token:
                    raise NonRetryableError("Slot taken")
                ctx['lock_token'] = token

            async def execute_create_appointment(self, ctx):
                ...

            async def compensate_release_lock(self, ctx):
                await self.cache.lock.release(...)
    """

    SAGA_TYPE: str
    STEPS: list = []
    COMPENSATIONS: dict = {}

    def __init__(self, session, cache):
        self.session = session
        self.cache = cache

    async def run(self, payload: dict) -> dict:
        saga = SagaState(
            saga_type=self.SAGA_TYPE, 
            payload=payload, 
            status="running",
            completed_steps=[],
            compensated_steps=[]
        )
        self.session.add(saga)
        await self.session.flush()

        ctx = {**payload, "_results": {}}

        try:
            for step in self.STEPS:
                saga.current_step = step
                await self.session.flush()

                result = await getattr(self, f"execute_{step}")(ctx)

                if result is not None:
                    ctx["_results"][step] = result
                saga.completed_steps = list(ctx["_results"].keys())

            saga.status = "completed"
            await self.session.flush()
            return ctx["_results"]

        except Exception as e:
            logger.error(f"Saga {saga.id} failed at {saga.current_step}: {e}")
            await self._compensate(saga, ctx, str(e))
            raise SagaFailedError(f"Saga failed: {e}", saga_id=str(saga.id)) from e

    async def _compensate(self, saga, ctx, error: str):
        saga.status = "compensating"
        saga.error = error

        done = list(reversed(saga.completed_steps or []))

        for step in done:
            comp = self.COMPENSATIONS.get(step)
            if not comp:
                continue
            try:
                await getattr(self, f"compensate_{comp}")(ctx)
                saga.compensated_steps = [*saga.compensated_steps, step]
                await self.session.flush()
            except Exception as comp_err:
                logger.error(f"Compensation {comp} failed: {comp_err}")

        saga.status = "failed"
        saga.failed_at = datetime.now()
        await self.session.flush()
