from datetime import date
from uuid import uuid4
import asyncio

import pytest

from Domain.value_objects.appointment_status import AppointmentStatus
from Domain.value_objects.payment_status import PaymentStatus
from infrastructure.consumers import payment_consumers as payment_consumers_module
from infrastructure.consumers.payment_consumers import _cancel_for_payment


class FakeAppointment:
    def __init__(self, status=AppointmentStatus.PENDING_PAYMENT):
        self.id = uuid4()
        self.patient_id = uuid4()
        self.doctor_id = uuid4()
        self.appointment_date = date(2026, 3, 30)
        self.status = status
        self.payment_status = PaymentStatus.PROCESSING
        self.cancelled_at = None
        self.cancelled_by = None
        self.cancel_reason = None


class FakeRepo:
    def __init__(self, appointment):
        self.appointment = appointment
        self.saved = []

    async def get_by_id_with_lock(self, appointment_id):
        await asyncio.sleep(0)
        if self.appointment and self.appointment.id == appointment_id:
            return self.appointment
        return None

    async def save(self, appointment):
        await asyncio.sleep(0)
        self.saved.append(appointment)


class _BeginCM:
    async def __aenter__(self):
        await asyncio.sleep(0)
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await asyncio.sleep(0)
        return False


class _SessionCM:
    def begin(self):
        return _BeginCM()

    async def __aenter__(self):
        await asyncio.sleep(0)
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await asyncio.sleep(0)
        return False


@pytest.mark.asyncio
async def test_cancel_for_payment_missing_appointment_id_raises():
    with pytest.raises(ValueError):
        await _cancel_for_payment(lambda: _SessionCM(), lambda _s: FakeRepo(None), {}, "payment_failed")


@pytest.mark.asyncio
async def test_cancel_for_payment_ignores_non_pending_payment(monkeypatch):
    appointment = FakeAppointment(status=AppointmentStatus.CONFIRMED)
    repo = FakeRepo(appointment)
    writes = []

    async def fake_write(session, **kwargs):
        await asyncio.sleep(0)
        writes.append(kwargs)

    monkeypatch.setattr(payment_consumers_module.OutboxWriter, "write", fake_write)

    await _cancel_for_payment(
        session_factory=lambda: _SessionCM(),
        appointment_repo_factory=lambda _s: repo,
        payload={"appointment_id": str(appointment.id)},
        reason="payment_failed",
    )

    assert repo.saved == []
    assert writes == []


@pytest.mark.asyncio
async def test_cancel_for_payment_updates_status_and_emits_events(monkeypatch):
    appointment = FakeAppointment(status=AppointmentStatus.PENDING_PAYMENT)
    repo = FakeRepo(appointment)
    writes = []

    async def fake_write(session, **kwargs):
        await asyncio.sleep(0)
        writes.append(kwargs)

    monkeypatch.setattr(payment_consumers_module.OutboxWriter, "write", fake_write)

    await _cancel_for_payment(
        session_factory=lambda: _SessionCM(),
        appointment_repo_factory=lambda _s: repo,
        payload={"appointment_id": str(appointment.id)},
        reason="payment_expired",
    )

    assert len(repo.saved) == 1
    assert appointment.status == AppointmentStatus.CANCELLED
    assert appointment.payment_status == PaymentStatus.UNPAID
    assert appointment.cancelled_by == "system"
    assert appointment.cancel_reason == "payment_expired"
    assert len(writes) == 2
    assert writes[0]["event_type"] == "appointment.cancelled"
    assert writes[1]["event_type"] == "cache.invalidate"
