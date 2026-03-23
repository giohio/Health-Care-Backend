from Application.use_cases.create_notification import CreateNotificationUseCase
from healthai_events import BaseConsumer
from infrastructure.repositories.notification_repository import NotificationRepository


class _NotificationConsumer(BaseConsumer):
    def __init__(self, connection, cache, session_factory, ws_manager):
        super().__init__(connection, cache)
        self._session_factory = session_factory
        self._ws_manager = ws_manager

    async def _create_notification(self, user_id: str, title: str, body: str, event_type: str):
        async with self._session_factory() as session:
            repo = NotificationRepository(session)
            use_case = CreateNotificationUseCase(repo, self._ws_manager)
            await use_case.execute(
                user_id=user_id,
                title=title,
                body=body,
                event_type=event_type,
            )
            await session.commit()


class AppointmentConfirmedConsumer(_NotificationConsumer):
    QUEUE = "notification.appointment.confirmed"
    EXCHANGE = "appointment_events"
    ROUTING_KEY = "appointment.confirmed"

    async def handle(self, payload: dict):
        auto_confirmed = payload.get("auto_confirmed", False)
        body = (
            "Your appointment is confirmed immediately by doctor auto-confirm settings."
            if auto_confirmed
            else "Your appointment has been confirmed by the doctor."
        )
        await self._create_notification(
            user_id=payload["patient_id"],
            title="Appointment Confirmed",
            body=body,
            event_type="appointment.confirmed",
        )


class AppointmentAutoConfirmedConsumer(_NotificationConsumer):
    QUEUE = "notification.appointment.auto_confirmed"
    EXCHANGE = "appointment_events"
    ROUTING_KEY = "appointment.auto_confirmed"

    async def handle(self, payload: dict):
        queue_number = payload.get("queue_number")
        queue_part = f" Queue #{queue_number}." if queue_number is not None else ""
        await self._create_notification(
            user_id=payload["patient_id"],
            title="Appointment Confirmed",
            body=f"Your appointment was auto-confirmed.{queue_part}",
            event_type="appointment.auto_confirmed",
        )


class AppointmentCreatedConsumer(_NotificationConsumer):
    QUEUE = "notification.appointment.created"
    EXCHANGE = "appointment_events"
    ROUTING_KEY = "appointment.created"

    async def handle(self, payload: dict):
        auto_confirmed = payload.get("auto_confirmed", False)
        if auto_confirmed:
            title = "New Appointment Added"
            body = "A new appointment was auto-confirmed and added to your schedule."
        else:
            title = "New Appointment Request"
            body = "A patient requested a new appointment. Please confirm or decline."
        await self._create_notification(
            user_id=payload["doctor_id"],
            title=title,
            body=body,
            event_type="appointment.created",
        )


class AppointmentCancelledConsumer(_NotificationConsumer):
    QUEUE = "notification.appointment.cancelled"
    EXCHANGE = "appointment_events"
    ROUTING_KEY = "appointment.cancelled"

    async def handle(self, payload: dict):
        await self._create_notification(
            user_id=payload["patient_id"],
            title="Appointment Cancelled",
            body="Your appointment was cancelled. Please book another slot.",
            event_type="appointment.cancelled",
        )


class AppointmentReminderConsumer(_NotificationConsumer):
    QUEUE = "notification.appointment.reminder"
    EXCHANGE = "appointment_events"
    ROUTING_KEY = "appointment.reminder"

    async def handle(self, payload: dict):
        await self._create_notification(
            user_id=payload["patient_id"],
            title="Appointment Reminder",
            body="Reminder: your appointment is coming up soon.",
            event_type="appointment.reminder",
        )
