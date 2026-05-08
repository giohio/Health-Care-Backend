"""
Consumers for triage events published by AI Service.
"""
import uuid as _uuid

from Application.use_cases.create_notification import CreateNotificationUseCase
from healthai_events.consumer import BaseConsumer
from healthai_events.exceptions import NonRetryableError


class _TriageConsumer(BaseConsumer):
    def __init__(self, connection, cache, session_factory, create_notification_use_case_factory, auth_client=None):
        super().__init__(connection, cache)
        self._session_factory = session_factory
        self._create_notification_use_case_factory = create_notification_use_case_factory
        self._auth_client = auth_client

    async def _create_notification(
        self,
        user_id: str,
        title: str,
        body: str,
        event_type: str,
        recipient_email: str | None = None,
        send_email: bool = False,
    ):
        if send_email and not recipient_email and self._auth_client:
            recipient_email = await self._auth_client.get_user_email(str(user_id))
        async with self._session_factory() as session:
            use_case: CreateNotificationUseCase = self._create_notification_use_case_factory(session)
            await use_case.execute(
                user_id=user_id,
                title=title,
                body=body,
                event_type=event_type,
                recipient_email=recipient_email,
                send_email=send_email,
            )
            await session.commit()


class TriageCompletedConsumer(_TriageConsumer):
    """
    Notify patient when their AI triage session has completed with a recommendation.
    Triggered by AI Service when a [R] recommendation is issued.
    """

    QUEUE = "notification.triage.completed"
    EXCHANGE = "triage_events"
    ROUTING_KEY = "triage.completed"

    async def handle(self, payload: dict):
        patient_id = payload.get("patient_id")
        if not patient_id:
            # Fallback: try to send to all notification channels
            return

        # Validate patient_id is a proper UUID before attempting DB write
        try:
            _uuid.UUID(str(patient_id))
        except ValueError as exc:
            raise NonRetryableError(f"Invalid patient_id UUID: {patient_id!r}") from exc

        department = payload.get("suggested_department") or payload.get("final_department") or "the appropriate department"
        urgency = payload.get("urgency_level") or "Normal"

        body = (
            f"AI Triage result: you are recommended to visit {department}.\n"
            f"Urgency level: {urgency}.\n"
            "Please book an appointment to complete the process."
        )

        await self._create_notification(
            user_id=patient_id,
            title="AI Triage Complete - Book Your Appointment",
            body=body,
            event_type="triage.completed",
            send_email=True,
        )
