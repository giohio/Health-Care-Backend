import logging
from typing import Any, Callable

from Domain.interfaces.appointment_repository import IAppointmentRepository
from healthai_events.consumer import BaseConsumer

logger = logging.getLogger(__name__)


class LabResultReadyConsumer(BaseConsumer):
    """Invalidate doctor queue cache when all lab results for an appointment are published."""

    QUEUE = "appointment.lab_results_ready"
    EXCHANGE = "lab_order_events"  # Same exchange as EMR Result Service
    ROUTING_KEY = "lab_order.all_results_ready"

    def __init__(
        self,
        connection,
        cache,
        session_factory,
        appointment_repo_factory: Callable[[Any], IAppointmentRepository],
    ):
        super().__init__(connection, cache)
        self._session_factory = session_factory
        self._appointment_repo_factory = appointment_repo_factory

    async def handle(self, payload: dict[str, Any]) -> None:
        """Handle lab_order.all_results_ready event to clear appointment queue cache."""
        logger.info("LabResultReadyConsumer received payload: %s", payload)
        
        appointment_id_raw = payload.get("appointment_id")
        if not appointment_id_raw:
            logger.warning("Missing appointment_id in lab_order.all_results_ready payload")
            return

        # Import here to avoid circular dependency
        import uuid
        appointment_id = uuid.UUID(str(appointment_id_raw))

        logger.info("Handling lab_order.all_results_ready for appointment %s", appointment_id)

        try:
            async with self._session_factory() as session:
                repo = self._appointment_repo_factory(session)
                appt = await repo.get_by_id(appointment_id)
                if not appt:
                    logger.warning("Appointment %s not found for cache invalidation", appointment_id)
                    return

                # Build cache key and invalidate
                cache_key = f"queue:{appt.doctor_id}:{appt.appointment_date}"
                if self._cache:
                    await self._cache.delete(cache_key)
                    logger.info("Invalidated queue cache key: %s", cache_key)
                else:
                    logger.warning("Cache is None, cannot invalidate")
        except Exception:
            logger.exception("Error handling lab_order.all_results_ready for appointment %s", appointment_id)
            # Don't raise - cache invalidation is best-effort
