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
        ai_referred = payload.get("ai_referred", False)
        urgency = payload.get("urgency_level")
        if ai_referred and urgency:
            body = (
                f"Your appointment is confirmed. "
                f"Urgency: {urgency}. "
                f"Your appointment was booked via AI Triage recommendation."
            )
        elif auto_confirmed:
            body = "Your appointment is confirmed immediately by doctor auto-confirm settings."
        else:
            body = "Your appointment has been confirmed by the doctor."
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
        ai_referred = payload.get("ai_referred", False)
        urgency = payload.get("urgency_level")
        if ai_referred and urgency:
            title = "Priority Patient from AI Triage"
            body = (
                f"A patient booked via AI Triage. "
                f"Priority: {urgency}. "
                "Please prioritize confirmation."
            )
        elif auto_confirmed:
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

        # Notify patient when their appointment is created
        patient_id = payload.get("patient_id")
        if patient_id:
            if ai_referred:
                patient_title = "Booking Successful"
                patient_body = (
                    f"You have booked via AI Triage. "
                    f"Priority: {urgency}. "
                    "Please wait for doctor confirmation."
                )
            else:
                patient_title = "Booking Successful"
                patient_body = "Your appointment is pending doctor confirmation."
            await self._create_notification(
                user_id=patient_id,
                title=patient_title,
                body=patient_body,
                event_type="appointment.created_patient",
                recipient_email=payload.get("patient_email"),
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
        redirect_dept = payload.get("redirect_department")
        if redirect_dept:
            body = (
                f"Your appointment request was declined by the doctor. "
                f"You have been referred to {redirect_dept} — "
                f"please book a new appointment with that department."
            )
            title = "Appointment Declined — Referral Issued"
        else:
            body = "Your appointment request was declined by the doctor."
            title = "Appointment Declined"

        await self._create_notification(
            user_id=payload["patient_id"],
            title=title,
            body=body,
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


class AppointmentOverdueConsumer(_NotificationConsumer):
    """
    Notify patient when their confirmed appointment has passed its scheduled time
    without starting (automatically marked OVERDUE by the scheduler).
    """

    QUEUE = "notification.appointment.overdue"
    EXCHANGE = "appointment_events"
    ROUTING_KEY = "appointment.overdue"

    async def handle(self, payload: dict):
        await self._create_notification(
            user_id=payload["patient_id"],
            title="Appointment Overdue",
            body=(
                "Your confirmed appointment time has passed without the appointment "
                "starting. If you still need to see the doctor, please contact the "
                "clinic or reschedule through the app."
            ),
            event_type="appointment.overdue",
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


class AppointmentAdjustedConsumer(_NotificationConsumer):
    """
    Notify all patients still waiting in the queue when a doctor extends or
    shortens the current appointment, giving them their new estimated start time.
    """

    QUEUE = "notification.appointment.adjusted"
    EXCHANGE = "appointment_events"
    ROUTING_KEY = "appointment.adjusted"

    async def handle(self, payload: dict):
        delay_minutes = payload.get("delay_minutes", 0)
        affected_patients: list[dict] = payload.get("affected_patients", [])

        if not affected_patients or delay_minutes == 0:
            return

        if delay_minutes > 0:
            direction = f"delayed by about {delay_minutes} minutes"
        else:
            direction = f"earlier by about {abs(delay_minutes)} minutes"

        for entry in affected_patients:
            patient_id = entry.get("patient_id")
            new_time = entry.get("new_estimated_start_time", "")
            if not patient_id:
                continue
            body = (
                f"The doctor is currently busy with the previous patient. "
                f"Your appointment may be {direction}. "
                f"New estimated time: {new_time}."
            )
            await self._create_notification(
                user_id=patient_id,
                title="Appointment Schedule Update",
                body=body,
                event_type="appointment.adjusted",
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
        payment_type = payload.get("payment_type", "APPOINTMENT")
        if payment_type == "LAB_ORDER":
            title = "Lab Order Payment Ready"
            body = "Your lab order payment is ready. Please complete payment so your doctor can proceed with lab tests."
        else:
            title = "Payment Created"
            body = "Your payment request is ready. Please complete payment to confirm appointment."
        await self._create_notification(
            user_id=payload["patient_id"],
            title=title,
            body=body,
            event_type="payment.created",
            recipient_email=payload.get("patient_email"),
            send_email=True,
        )


class LabResultPublishedConsumer(_NotificationConsumer):
    QUEUE = "notification.lab_result.published"
    EXCHANGE = "lab_order_events"
    ROUTING_KEY = "lab_result.published"

    async def handle(self, payload: dict):
        test_name = payload.get("test_name") or "lab result"
        await self._create_notification(
            user_id=payload["patient_id"],
            title="Lab Result Ready",
            body=f"Your {test_name} result is ready for review.",
            event_type="lab_result.published",
            recipient_email=payload.get("patient_email"),
            send_email=True,
        )


class LabOrderAllResultsReadyConsumer(_NotificationConsumer):
    QUEUE = "notification.lab_order.all_results_ready"
    EXCHANGE = "lab_order_events"
    ROUTING_KEY = "lab_order.all_results_ready"

    async def handle(self, payload: dict):
        total_results = payload.get("total_results")
        if total_results:
            body = f"All {total_results} lab results for your appointment are now ready."
        else:
            body = "All lab results for your appointment are now ready."

        await self._create_notification(
            user_id=payload["patient_id"],
            title="All Lab Results Ready",
            body=body,
            event_type="lab_order.all_results_ready",
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


class AIReferredReviewConsumer(_NotificationConsumer):
    """
    Notify General Medicine doctor when an AI-referred appointment
    requires their priority review (regardless of auto_confirm setting).

    Triggered by PaymentPaidConsumer when ai_referred=True and
    referred_by_doctor_id is set on the appointment.
    """

    QUEUE = "notification.appointment.ai_referred_review"
    EXCHANGE = "appointment_events"
    ROUTING_KEY = "appointment.ai_referred_review"

    async def handle(self, payload: dict):
        urgency = payload.get("urgency_level") or "Normal"
        appt_date = payload.get("appointment_date", "N/A")
        appt_time = payload.get("start_time", "N/A")

        body = (
            f"A patient referred via AI triage with priority: {urgency}.\n"
            f"Date: {appt_date} at {appt_time}.\n"
            "Please prioritize reviewing and confirming the appointment."
        )
        await self._create_notification(
            user_id=payload["doctor_id"],
            title="Priority Patient from AI Triage",
            body=body,
            event_type="appointment.ai_referred_review",
            send_email=True,
        )
