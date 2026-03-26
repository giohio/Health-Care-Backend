import asyncio
from datetime import date, time
from uuid import uuid4

import pytest
from Application.use_cases.get_doctor_queue import GetDoctorQueueUseCase
from Domain.value_objects.appointment_status import AppointmentStatus


class FakeAppointment:
    def __init__(self, doctor_id, appointment_date, queue_number=1, status=AppointmentStatus.CONFIRMED):
        self.id = uuid4()
        self.patient_id = uuid4()
        self.doctor_id = doctor_id
        self.specialty_id = uuid4()
        self.appointment_date = appointment_date
        self.start_time = time(10, 0)
        self.end_time = time(10, 30)
        self.appointment_type = "general"
        self.chief_complaint = "Fever"
        self.queue_number = queue_number
        self.status = status


class FakeRepo:
    def __init__(self, appointments=None):
        self.appointments = appointments or []

    async def get_doctor_queue(self, doctor_id, appointment_date):
        await asyncio.sleep(0)
        return [a for a in self.appointments if a.doctor_id == doctor_id and a.appointment_date == appointment_date]


class FakeDoctorClient:
    def __init__(self, patient_contexts=None):
        self.patient_contexts = patient_contexts or {}

    async def get_patient_full_context(self, patient_id):
        await asyncio.sleep(0)
        return self.patient_contexts.get(patient_id)


@pytest.mark.asyncio
async def test_get_doctor_queue_returns_appointments_for_date():
    doctor_id = uuid4()
    patient_id1 = uuid4()
    patient_id2 = uuid4()
    appointment_date = date(2026, 3, 30)

    appt1 = FakeAppointment(doctor_id=doctor_id, appointment_date=appointment_date)
    appt1.patient_id = patient_id1
    appt1.queue_number = 1

    appt2 = FakeAppointment(doctor_id=doctor_id, appointment_date=appointment_date)
    appt2.patient_id = patient_id2
    appt2.queue_number = 2

    repo = FakeRepo([appt1, appt2])
    patient_contexts = {
        str(patient_id1): {"full_name": "John Doe"},
        str(patient_id2): {"full_name": "Jane Smith"},
    }
    doctor_client = FakeDoctorClient(patient_contexts=patient_contexts)

    use_case = GetDoctorQueueUseCase(appointment_repo=repo, doctor_client=doctor_client)
    result = await use_case.execute(doctor_id=doctor_id, appointment_date=appointment_date)

    assert len(result) == 2
    assert result[0]["queue_number"] == 1
    assert result[0]["patient_name"] == "John Doe"
    assert result[1]["queue_number"] == 2
    assert result[1]["patient_name"] == "Jane Smith"


@pytest.mark.asyncio
async def test_get_doctor_queue_returns_empty_when_no_appointments():
    doctor_id = uuid4()
    appointment_date = date(2026, 3, 30)

    repo = FakeRepo([])
    doctor_client = FakeDoctorClient()

    use_case = GetDoctorQueueUseCase(appointment_repo=repo, doctor_client=doctor_client)
    result = await use_case.execute(doctor_id=doctor_id, appointment_date=appointment_date)

    assert len(result) == 0


@pytest.mark.asyncio
async def test_get_doctor_queue_filters_by_doctor_id():
    doctor_id1 = uuid4()
    doctor_id2 = uuid4()
    appointment_date = date(2026, 3, 30)

    appt1 = FakeAppointment(doctor_id=doctor_id1, appointment_date=appointment_date)
    appt2 = FakeAppointment(doctor_id=doctor_id2, appointment_date=appointment_date)

    repo = FakeRepo([appt1, appt2])
    doctor_client = FakeDoctorClient()

    use_case = GetDoctorQueueUseCase(appointment_repo=repo, doctor_client=doctor_client)
    result = await use_case.execute(doctor_id=doctor_id1, appointment_date=appointment_date)

    assert len(result) == 1
    assert result[0]["patient_id"] == str(appt1.patient_id)


@pytest.mark.asyncio
async def test_get_doctor_queue_filters_by_appointment_date():
    doctor_id = uuid4()
    date1 = date(2026, 3, 30)
    date2 = date(2026, 4, 1)

    appt1 = FakeAppointment(doctor_id=doctor_id, appointment_date=date1)
    appt2 = FakeAppointment(doctor_id=doctor_id, appointment_date=date2)

    repo = FakeRepo([appt1, appt2])
    doctor_client = FakeDoctorClient()

    use_case = GetDoctorQueueUseCase(appointment_repo=repo, doctor_client=doctor_client)
    result = await use_case.execute(doctor_id=doctor_id, appointment_date=date1)

    assert len(result) == 1
    assert result[0]["appointment_date"] == str(date1)


@pytest.mark.asyncio
async def test_get_doctor_queue_includes_all_appointment_fields():
    doctor_id = uuid4()
    patient_id = uuid4()
    appointment_date = date(2026, 3, 30)

    appt = FakeAppointment(doctor_id=doctor_id, appointment_date=appointment_date, status=AppointmentStatus.CONFIRMED)
    appt.patient_id = patient_id
    appt.chief_complaint = "Severe headache"
    appt.appointment_type = "specialized"

    repo = FakeRepo([appt])
    patient_contexts = {str(patient_id): {"full_name": "Test Patient"}}
    doctor_client = FakeDoctorClient(patient_contexts=patient_contexts)

    use_case = GetDoctorQueueUseCase(appointment_repo=repo, doctor_client=doctor_client)
    result = await use_case.execute(doctor_id=doctor_id, appointment_date=appointment_date)

    assert result[0]["appointment_id"] == str(appt.id)
    assert result[0]["patient_id"] == str(patient_id)
    assert result[0]["patient_name"] == "Test Patient"
    assert result[0]["appointment_date"] == str(appointment_date)
    assert result[0]["start_time"] == str(time(10, 0))
    assert result[0]["end_time"] == str(time(10, 30))
    assert result[0]["status"] == AppointmentStatus.CONFIRMED
    assert result[0]["appointment_type"] == "specialized"
    assert result[0]["chief_complaint"] == "Severe headache"


@pytest.mark.asyncio
async def test_get_doctor_queue_handles_missing_patient_context():
    doctor_id = uuid4()
    patient_id = uuid4()
    appointment_date = date(2026, 3, 30)

    appt = FakeAppointment(doctor_id=doctor_id, appointment_date=appointment_date)
    appt.patient_id = patient_id

    repo = FakeRepo([appt])
    doctor_client = FakeDoctorClient(patient_contexts={})

    use_case = GetDoctorQueueUseCase(appointment_repo=repo, doctor_client=doctor_client)
    result = await use_case.execute(doctor_id=doctor_id, appointment_date=appointment_date)

    assert len(result) == 1
    assert result[0]["patient_name"] is None
