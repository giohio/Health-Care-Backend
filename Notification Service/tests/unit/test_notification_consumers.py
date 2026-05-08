import asyncio

import pytest
from infrastructure.consumers.appointment_events_consumers import (
    AppointmentAutoConfirmedConsumer,
    AppointmentCancelledConsumer,
    AppointmentCompletedConsumer,
    AppointmentConfirmedConsumer,
    AppointmentCreatedConsumer,
    AppointmentDeclinedConsumer,
    AppointmentNoShowConsumer,
    AppointmentOverdueConsumer,
    AppointmentReminderConsumer,
    AppointmentRescheduledConsumer,
    AppointmentStartedConsumer,
    LabOrderAllResultsReadyConsumer,
    LabResultPublishedConsumer,
    PaymentCreatedConsumer,
    PaymentExpiredConsumer,
    PaymentFailedConsumer,
    PaymentPaidConsumer,
    PaymentRefundedConsumer,
)


class FakeSession:
    def __init__(self):
        self.commits = 0

    async def commit(self):
        await asyncio.sleep(0)
        self.commits += 1


class SessionFactory:
    def __call__(self):
        return self

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def __init__(self):
        self.session = FakeSession()


class FakeCreateNotificationUC:
    def __init__(self, sink):
        self.sink = sink

    async def execute(self, **kwargs):
        await asyncio.sleep(0)
        self.sink.append(kwargs)


def _factory(sink):
    return lambda _session: FakeCreateNotificationUC(sink)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "consumer_cls,payload,expected_event",
    [
        (AppointmentConfirmedConsumer, {"patient_id": "u1", "auto_confirmed": True}, "appointment.confirmed"),
        (AppointmentAutoConfirmedConsumer, {"patient_id": "u2", "queue_number": 7}, "appointment.auto_confirmed"),
        (AppointmentCreatedConsumer, {"doctor_id": "d1", "auto_confirmed": False}, "appointment.created"),
        (AppointmentDeclinedConsumer, {"patient_id": "u3"}, "appointment.declined"),
        (AppointmentRescheduledConsumer, {"doctor_id": "d2"}, "appointment.rescheduled"),
        (AppointmentNoShowConsumer, {"patient_id": "u4"}, "appointment.no_show"),
        (AppointmentCompletedConsumer, {"patient_id": "u5"}, "appointment.completed"),
        (AppointmentStartedConsumer, {"patient_id": "u12"}, "appointment.started"),
        (LabResultPublishedConsumer, {"patient_id": "u13", "test_name": "CBC"}, "lab_result.published"),
        (LabOrderAllResultsReadyConsumer, {"patient_id": "u14", "total_results": 2}, "lab_order.all_results_ready"),
        (PaymentFailedConsumer, {"patient_id": "u6"}, "payment.failed"),
        (PaymentCreatedConsumer, {"patient_id": "u7"}, "payment.created"),
        (PaymentPaidConsumer, {"patient_id": "u8"}, "payment.paid"),
        (PaymentExpiredConsumer, {"patient_id": "u9"}, "payment.expired"),
        (PaymentRefundedConsumer, {"patient_id": "u10"}, "payment.refunded"),
        (AppointmentReminderConsumer, {"patient_id": "u11"}, "appointment.reminder"),
        (AppointmentOverdueConsumer, {"patient_id": "u15"}, "appointment.overdue"),
    ],
)
async def test_consumers_create_notification_and_commit(consumer_cls, payload, expected_event):
    sink = []
    sf = SessionFactory()
    consumer = consumer_cls(
        connection=object(),
        cache=object(),
        session_factory=sf,
        create_notification_use_case_factory=_factory(sink),
    )

    await consumer.handle(payload)

    assert len(sink) == 1
    assert sink[0]["event_type"] == expected_event
    assert sink[0]["send_email"] is True
    assert sf.session.commits == 1


@pytest.mark.asyncio
async def test_appointment_cancelled_branches_and_missing_target():
    sink = []
    sf = SessionFactory()
    consumer = AppointmentCancelledConsumer(
        connection=object(),
        cache=object(),
        session_factory=sf,
        create_notification_use_case_factory=_factory(sink),
    )

    # Patient cancels → patient gets confirmation + doctor gets notification (2 notifications)
    await consumer.handle({"cancelled_by": "patient", "patient_id": "p1", "doctor_id": "d1"})
    assert len(sink) == 2
    user_ids = {n["user_id"] for n in sink}
    assert "p1" in user_ids
    assert "d1" in user_ids
    # patient message is confirmation, doctor message is schedule change
    patient_notif = next(n for n in sink if n["user_id"] == "p1")
    assert "confirmed" in patient_notif["body"].lower()

    sink.clear()

    # Doctor cancels → only patient notified
    await consumer.handle({"cancelled_by": "doctor", "patient_id": "p2", "doctor_id": "d2"})
    assert len(sink) == 1
    assert sink[0]["user_id"] == "p2"

    sink.clear()

    # System cancels → only patient notified
    await consumer.handle({"cancelled_by": "system", "patient_id": "p3"})
    assert len(sink) == 1
    assert sink[0]["user_id"] == "p3"

    sink.clear()

    # Missing patient_id → no notification
    await consumer.handle({"cancelled_by": "patient", "doctor_id": "d3"})
    assert len(sink) == 1  # only the doctor notification since patient_id is missing
    assert sink[0]["user_id"] == "d3"

    sink.clear()

    # Missing both → no notification
    await consumer.handle({"cancelled_by": "doctor"})
    assert len(sink) == 0


@pytest.mark.asyncio
async def test_payment_created_consumer_uses_lab_order_copy_for_lab_payments():
    sink = []
    sf = SessionFactory()
    consumer = PaymentCreatedConsumer(
        connection=object(),
        cache=object(),
        session_factory=sf,
        create_notification_use_case_factory=_factory(sink),
    )

    await consumer.handle({"patient_id": "p1", "payment_type": "LAB_ORDER"})

    assert sink[0]["title"] == "Lab Order Payment Ready"
    assert "lab order payment" in sink[0]["body"].lower()


@pytest.mark.asyncio
async def test_lab_result_published_consumer_includes_test_name():
    sink = []
    sf = SessionFactory()
    consumer = LabResultPublishedConsumer(
        connection=object(),
        cache=object(),
        session_factory=sf,
        create_notification_use_case_factory=_factory(sink),
    )

    await consumer.handle({"patient_id": "p2", "test_name": "Lipid Panel"})

    assert sink[0]["title"] == "Lab Result Ready"
    assert "lipid panel" in sink[0]["body"].lower()


@pytest.mark.asyncio
async def test_all_results_ready_consumer_mentions_total_when_present():
    sink = []
    sf = SessionFactory()
    consumer = LabOrderAllResultsReadyConsumer(
        connection=object(),
        cache=object(),
        session_factory=sf,
        create_notification_use_case_factory=_factory(sink),
    )

    await consumer.handle({"patient_id": "p3", "total_results": 3})

    assert sink[0]["title"] == "All Lab Results Ready"
    assert "all 3 lab results" in sink[0]["body"].lower()
