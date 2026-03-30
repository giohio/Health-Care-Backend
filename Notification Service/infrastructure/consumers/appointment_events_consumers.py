from Application.use_cases.create_notification import CreateNotificationUseCase
from healthai_events.consumer import BaseConsumer


class _NotificationConsumer(BaseConsumer):
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
            recipient_email=payload.get("patient_email"),
            send_email=True,
        )


class AppointmentStartedConsumer(_NotificationConsumer):
    QUEUE = "notification.appointment.started"
    EXCHANGE = "appointment_events"
    ROUTING_KEY = "appointment.started"

    async def handle(self, payload: dict):
        await self._create_notification(
            user_id=payload["patient_id"],
            title="Appointment Started",
            body="Your appointment has started, please proceed to the examination room",
            event_type="appointment.started",
            recipient_email=payload.get("patient_email"),
            send_email=True,
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
            recipient_email=payload.get("patient_email"),
            send_email=True,
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
            recipient_email=payload.get("doctor_email"),
            send_email=True,
        )


class AppointmentCancelledConsumer(_NotificationConsumer):
    QUEUE = "notification.appointment.cancelled"
    EXCHANGE = "appointment_events"
    ROUTING_KEY = "appointment.cancelled"

    async def handle(self, payload: dict):
        cancelled_by = (payload.get("cancelled_by") or "").lower()
        is_patient_cancel = cancelled_by == "patient"

        patient_id = payload.get("patient_id")
        doctor_id = payload.get("doctor_id")

        if patient_id:
            patient_body = (
                "Your appointment cancellation is confirmed."
                if is_patient_cancel
                else "Your appointment was cancelled. Please book another slot."
            )
            await self._create_notification(
                user_id=patient_id,
                title="Appointment Cancelled",
                body=patient_body,
                event_type="appointment.cancelled",
                recipient_email=payload.get("patient_email"),
                send_email=True,
            )

        if is_patient_cancel and doctor_id:
            await self._create_notification(
                user_id=doctor_id,
                title="Appointment Cancelled",
                body="A patient cancelled an appointment in your schedule.",
                event_type="appointment.cancelled",
                recipient_email=payload.get("doctor_email"),
                send_email=True,
            )


class AppointmentDeclinedConsumer(_NotificationConsumer):
    QUEUE = "notification.appointment.declined"
    EXCHANGE = "appointment_events"
    ROUTING_KEY = "appointment.declined"

    async def handle(self, payload: dict):
        await self._create_notification(
            user_id=payload["patient_id"],
            title="Appointment Declined",
            body="Your appointment request was declined by the doctor.",
            event_type="appointment.declined",
            recipient_email=payload.get("patient_email"),
            send_email=True,
        )


class AppointmentRescheduledConsumer(_NotificationConsumer):
    QUEUE = "notification.appointment.rescheduled"
    EXCHANGE = "appointment_events"
    ROUTING_KEY = "appointment.rescheduled"

    async def handle(self, payload: dict):
        await self._create_notification(
            user_id=payload["doctor_id"],
            title="Appointment Rescheduled",
            body="A patient has Rescheduled an appointment. Please review and reconfirm.",
            event_type="appointment.rescheduled",
            recipient_email=payload.get("doctor_email"),
            send_email=True,
        )


class AppointmentNoShowConsumer(_NotificationConsumer):
    QUEUE = "notification.appointment.no_show"
    EXCHANGE = "appointment_events"
    ROUTING_KEY = "appointment.no_show"

    async def handle(self, payload: dict):
        await self._create_notification(
            user_id=payload["patient_id"],
            title="Appointment no-show",
            body="You were marked as no-show for this appointment.",
            event_type="appointment.no_show",
            recipient_email=payload.get("patient_email"),
            send_email=True,
        )


class AppointmentCompletedConsumer(_NotificationConsumer):
    QUEUE = "notification.appointment.completed"
    EXCHANGE = "appointment_events"
    ROUTING_KEY = "appointment.completed"

    async def handle(self, payload: dict):
        await self._create_notification(
            user_id=payload["patient_id"],
            title="Appointment Completed",
            body="Your appointment has been Completed successfully.",
            event_type="appointment.completed",
            recipient_email=payload.get("patient_email"),
            send_email=True,
        )


class PaymentFailedConsumer(_NotificationConsumer):
    QUEUE = "notification.payment.failed"
    EXCHANGE = "payment_events"
    ROUTING_KEY = "payment.failed"

    async def handle(self, payload: dict):
        await self._create_notification(
            user_id=payload["patient_id"],
            title="Payment Failed",
            body="Your payment failed. Please retry booking/payment.",
            event_type="payment.failed",
            recipient_email=payload.get("patient_email"),
            send_email=True,
        )


class PaymentCreatedConsumer(_NotificationConsumer):
    QUEUE = "notification.payment.created"
    EXCHANGE = "payment_events"
    ROUTING_KEY = "payment.created"

    async def handle(self, payload: dict):
        await self._create_notification(
            user_id=payload["patient_id"],
            title="Payment Created",
            body="Your payment request is ready. Please complete payment to confirm appointment.",
            event_type="payment.created",
            recipient_email=payload.get("patient_email"),
            send_email=True,
        )


class PaymentPaidConsumer(_NotificationConsumer):
    QUEUE = "notification.payment.paid"
    EXCHANGE = "payment_events"
    ROUTING_KEY = "payment.paid"

    async def handle(self, payload: dict):
        await self._create_notification(
            user_id=payload["patient_id"],
            title="Payment Successful",
            body="Your payment was successful.",
            event_type="payment.paid",
            recipient_email=payload.get("patient_email"),
            send_email=True,
        )


class PaymentExpiredConsumer(_NotificationConsumer):
    QUEUE = "notification.payment.expired"
    EXCHANGE = "payment_events"
    ROUTING_KEY = "payment.expired"

    async def handle(self, payload: dict):
        await self._create_notification(
            user_id=payload["patient_id"],
            title="Payment Expired",
            body="Your payment window has expired. Please book again if needed.",
            event_type="payment.expired",
            recipient_email=payload.get("patient_email"),
            send_email=True,
        )


class PaymentRefundedConsumer(_NotificationConsumer):
    QUEUE = "notification.payment.refunded"
    EXCHANGE = "payment_events"
    ROUTING_KEY = "payment.refunded"

    async def handle(self, payload: dict):
        await self._create_notification(
            user_id=payload["patient_id"],
            title="Payment Refunded",
            body="Your payment has been refunded.",
            event_type="payment.refunded",
            recipient_email=payload.get("patient_email"),
            send_email=True,
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
            recipient_email=payload.get("patient_email"),
            send_email=True,
        )
