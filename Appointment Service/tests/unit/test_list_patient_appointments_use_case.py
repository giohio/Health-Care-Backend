from datetime import date, time
from uuid import uuid4
import asyncio

import pytest

from Application.use_cases.list_patient_appointments import ListPatientAppointmentsUseCase
from Domain.value_objects.appointment_status import AppointmentStatus
from Domain.value_objects.payment_status import PaymentStatus


class FakeAppointment:
    def __init__(self, patient_id, appointment_date, status=AppointmentStatus.PENDING):
        self.id = uuid4()
        self.patient_id = patient_id
        self.doctor_id = uuid4()
        self.specialty_id = uuid4()
        self.appointment_date = appointment_date
        self.start_time = time(10, 0)
        self.end_time = time(10, 30)
        self.appointment_type = "general"
        self.chief_complaint = None
        self.note_for_doctor = None
        self.status = status
        self.payment_status = PaymentStatus.PAID
        self.queue_number = None


class FakeRepo:
    def __init__(self, appointments=None):
        self.appointments = appointments or []

    async def list_by_patient(self, patient_id):
        await asyncio.sleep(0)
        return [a for a in self.appointments if a.patient_id == patient_id]


@pytest.mark.asyncio
async def test_list_patient_appointments_returns_all_appointments():
    patient_id = uuid4()
    appt1 = FakeAppointment(patient_id=patient_id, appointment_date=date(2026, 3, 30))
    appt2 = FakeAppointment(patient_id=patient_id, appointment_date=date(2026, 4, 1))
    other_patient_appt = FakeAppointment(patient_id=uuid4(), appointment_date=date(2026, 3, 30))

    repo = FakeRepo([appt1, appt2, other_patient_appt])
    use_case = ListPatientAppointmentsUseCase(appointment_repo=repo)

    results = await use_case.execute(patient_id=patient_id)

    assert len(results) == 2
    assert results[0].id == appt1.id
    assert results[1].id == appt2.id


@pytest.mark.asyncio
async def test_list_patient_appointments_returns_empty_for_no_appointments():
    patient_id = uuid4()
    repo = FakeRepo([])
    use_case = ListPatientAppointmentsUseCase(appointment_repo=repo)

    results = await use_case.execute(patient_id=patient_id)

    assert len(results) == 0


@pytest.mark.asyncio
async def test_list_patient_appointments_filters_by_patient_id():
    patient1 = uuid4()
    patient2 = uuid4()
    appt1 = FakeAppointment(patient_id=patient1, appointment_date=date(2026, 3, 30))
    appt2 = FakeAppointment(patient_id=patient2, appointment_date=date(2026, 3, 30))

    repo = FakeRepo([appt1, appt2])
    use_case = ListPatientAppointmentsUseCase(appointment_repo=repo)

    results = await use_case.execute(patient_id=patient1)

    assert len(results) == 1
    assert results[0].patient_id == patient1


@pytest.mark.asyncio
async def test_list_patient_appointments_returns_different_statuses():
    patient_id = uuid4()
    appt1 = FakeAppointment(
        patient_id=patient_id,
        appointment_date=date(2026, 3, 30),
        status=AppointmentStatus.PENDING,
    )
    appt2 = FakeAppointment(
        patient_id=patient_id,
        appointment_date=date(2026, 4, 1),
        status=AppointmentStatus.CONFIRMED,
    )
    appt3 = FakeAppointment(
        patient_id=patient_id,
        appointment_date=date(2026, 4, 5),
        status=AppointmentStatus.COMPLETED,
    )

    repo = FakeRepo([appt1, appt2, appt3])
    use_case = ListPatientAppointmentsUseCase(appointment_repo=repo)

    results = await use_case.execute(patient_id=patient_id)

    assert len(results) == 3
    assert results[0].status == AppointmentStatus.PENDING
    assert results[1].status == AppointmentStatus.CONFIRMED
    assert results[2].status == AppointmentStatus.COMPLETED
