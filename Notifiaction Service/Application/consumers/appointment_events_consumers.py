from Application.use_cases.create_notification import CreateNotificationUseCase
from healthai_events import BaseConsumer
from infrastructure.repositories.notification_repository import NotificationRepository


class AppointmentConfirmedConsumer(BaseConsumer):
    QUEUE = "notification.appointment.confirmed"
    EXCHANGE = "appointment_events"
    ROUTING_KEY = "appointment.confirmed"

    def __init__(self, connection, cache, session_factory, ws_manager):
        super().__init__(connection, cache)
        self._session_factory = session_factory
        self._ws_manager = ws_manager

    async def _create_notification(self, payload: dict, title: str, body: str, event_type: str):
        async with self._session_factory() as session:
            repo = NotificationRepository(session)
            use_case = CreateNotificationUseCase(repo, self._ws_manager)
            await use_case.execute(
                user_id=payload["patient_id"],
                title=title,
                body=body,
                event_type=event_type,
            )
            await session.commit()

    async def handle(self, payload: dict):
        await self._create_notification(
            payload=payload,
            title="Appointment Confirmed",
            body="Your appointment has been confirmed by the doctor.",
            event_type="appointment.confirmed",
        )


class AppointmentCancelledConsumer(BaseConsumer):
    QUEUE = "notification.appointment.cancelled"
    EXCHANGE = "appointment_events"
    ROUTING_KEY = "appointment.cancelled"

    def __init__(self, connection, cache, session_factory, ws_manager):
        super().__init__(connection, cache)
        self._session_factory = session_factory
        self._ws_manager = ws_manager

    async def _create_notification(self, payload: dict, title: str, body: str, event_type: str):
        async with self._session_factory() as session:
            repo = NotificationRepository(session)
            use_case = CreateNotificationUseCase(repo, self._ws_manager)
            await use_case.execute(
                user_id=payload["patient_id"],
                title=title,
                body=body,
                event_type=event_type,
            )
            await session.commit()

    async def handle(self, payload: dict):
        await self._create_notification(
            payload=payload,
            title="Appointment Cancelled",
            body="Your appointment was cancelled. Please book another slot.",
            event_type="appointment.cancelled",
        )


class AppointmentReminderConsumer(BaseConsumer):
    QUEUE = "notification.appointment.reminder"
    EXCHANGE = "appointment_events"
    ROUTING_KEY = "appointment.reminder"

    def __init__(self, connection, cache, session_factory, ws_manager):
        super().__init__(connection, cache)
        self._session_factory = session_factory
        self._ws_manager = ws_manager

    async def _create_notification(self, payload: dict, title: str, body: str, event_type: str):
        async with self._session_factory() as session:
            repo = NotificationRepository(session)
            use_case = CreateNotificationUseCase(repo, self._ws_manager)
            await use_case.execute(
                user_id=payload["patient_id"],
                title=title,
                body=body,
                event_type=event_type,
            )
            await session.commit()

    async def handle(self, payload: dict):
        await self._create_notification(
            payload=payload,
            title="Appointment Reminder",
            body="Reminder: your appointment is coming up soon.",
            event_type="appointment.reminder",
        )
