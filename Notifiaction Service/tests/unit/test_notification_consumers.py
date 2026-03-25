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
    AppointmentReminderConsumer,
    AppointmentRescheduledConsumer,
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
        (PaymentFailedConsumer, {"patient_id": "u6"}, "payment.failed"),
        (PaymentCreatedConsumer, {"patient_id": "u7"}, "payment.created"),
        (PaymentPaidConsumer, {"patient_id": "u8"}, "payment.paid"),
        (PaymentExpiredConsumer, {"patient_id": "u9"}, "payment.expired"),
        (PaymentRefundedConsumer, {"patient_id": "u10"}, "payment.refunded"),
        (AppointmentReminderConsumer, {"patient_id": "u11"}, "appointment.reminder"),
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

    await consumer.handle({"cancelled_by": "patient", "doctor_id": "d1"})
    assert sink[-1]["user_id"] == "d1"

    await consumer.handle({"cancelled_by": "doctor", "patient_id": "p1"})
    assert sink[-1]["user_id"] == "p1"

    before = len(sink)
    await consumer.handle({"cancelled_by": "patient"})
    assert len(sink) == before
