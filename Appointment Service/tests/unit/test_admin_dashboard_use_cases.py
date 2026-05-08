from datetime import date, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from Application.use_cases.get_admin_chart_data import GetAdminChartDataUseCase
from Application.use_cases.get_admin_stats import GetAdminStatsUseCase
from Domain.value_objects.appointment_status import AppointmentStatus
from Domain.value_objects.payment_status import PaymentStatus


class FakeRepo:
    def __init__(self, appointments):
        self.appointments = appointments
        self.calls = []

    async def list_all(self, date_from, date_to):
        self.calls.append((date_from, date_to))
        return self.appointments


class FakeDoctorClient:
    def __init__(self, specialties=None, exc=None):
        self.specialties = specialties or []
        self.exc = exc

    async def get_specialties(self):
        if self.exc:
            raise self.exc
        return self.specialties


def _appointment(appt_date, specialty_id, status, payment_status, fee):
    return SimpleNamespace(
        id=uuid4(),
        appointment_date=appt_date,
        specialty_id=specialty_id,
        status=status,
        payment_status=payment_status,
        consultation_fee=fee,
    )


@pytest.mark.asyncio
async def test_get_admin_stats_aggregates_and_enriches_specialty_names(monkeypatch):
    today = date(2026, 4, 2)

    class FakeDate(date):
        @classmethod
        def today(cls):
            return today

    monkeypatch.setattr("Application.use_cases.get_admin_stats.date", FakeDate)

    spec_a = uuid4()
    spec_b = uuid4()
    appointments = [
        _appointment(today, spec_a, AppointmentStatus.COMPLETED, PaymentStatus.PAID, 300000),
        _appointment(today, spec_a, AppointmentStatus.CANCELLED, PaymentStatus.UNPAID, 0),
        _appointment(today, spec_b, AppointmentStatus.NO_SHOW, PaymentStatus.PAID, 200000),
        _appointment(today, spec_b, AppointmentStatus.PENDING_PAYMENT, PaymentStatus.PROCESSING, 0),
    ]
    repo = FakeRepo(appointments)
    doctor_client = FakeDoctorClient(
        specialties=[
            {"id": str(spec_a), "name": "Tim mach"},
            {"id": str(spec_b), "name": "Da lieu"},
        ]
    )

    use_case = GetAdminStatsUseCase(appointment_repo=repo, doctor_client=doctor_client)
    result = await use_case.execute(range_type="week")

    data = result["data"]
    assert result["status"] == "success"
    assert data["total_appointments"] == 4
    assert data["total_revenue"] == 500000
    assert data["by_status"]["completed"] == 1
    assert data["by_status"]["cancelled"] == 1
    assert data["by_status"]["no_show"] == 1
    assert data["completion_rate"] == 33.3
    assert data["cancellation_rate"] == 25.0

    by_specialty = {row["specialty_id"]: row for row in data["by_specialty"]}
    assert by_specialty[str(spec_a)]["specialty_name"] == "Tim mach"
    assert by_specialty[str(spec_a)]["revenue"] == 300000
    assert by_specialty[str(spec_b)]["specialty_name"] == "Da lieu"
    assert by_specialty[str(spec_b)]["revenue"] == 200000


@pytest.mark.asyncio
async def test_get_admin_stats_falls_back_when_doctor_service_fails(monkeypatch):
    today = date(2026, 4, 2)

    class FakeDate(date):
        @classmethod
        def today(cls):
            return today

    monkeypatch.setattr("Application.use_cases.get_admin_stats.date", FakeDate)

    spec = uuid4()
    repo = FakeRepo([
        _appointment(today, spec, AppointmentStatus.CONFIRMED, PaymentStatus.UNPAID, 0),
    ])
    use_case = GetAdminStatsUseCase(appointment_repo=repo, doctor_client=FakeDoctorClient(exc=RuntimeError("down")))

    result = await use_case.execute(range_type="month")

    assert result["status"] == "success"
    assert result["data"]["by_specialty"][0]["specialty_name"] == str(spec)


@pytest.mark.asyncio
async def test_get_admin_chart_data_zero_fills_and_detects_peak(monkeypatch):
    today = date(2026, 4, 2)

    class FakeDate(date):
        @classmethod
        def today(cls):
            return today

    monkeypatch.setattr("Application.use_cases.get_admin_chart_data.date", FakeDate)

    d1 = today - timedelta(days=2)
    d2 = today
    spec = uuid4()
    repo = FakeRepo(
        [
            _appointment(d1, spec, AppointmentStatus.PENDING, PaymentStatus.UNPAID, 0),
            _appointment(d1, spec, AppointmentStatus.PENDING, PaymentStatus.UNPAID, 0),
            _appointment(d2, spec, AppointmentStatus.CONFIRMED, PaymentStatus.UNPAID, 0),
        ]
    )

    use_case = GetAdminChartDataUseCase(appointment_repo=repo)
    result = await use_case.execute(range_type="week", metric="appointments")

    data = result["data"]
    assert result["status"] == "success"
    assert data["metric"] == "appointments"
    assert len(data["data_points"]) == 7
    assert data["total"] == 3
    assert data["peak_day"]["date"] == str(d1)
    assert data["peak_day"]["value"] == 2
    assert any(point["value"] == 0 for point in data["data_points"])


@pytest.mark.asyncio
async def test_get_admin_chart_data_revenue_counts_paid_only(monkeypatch):
    today = date(2026, 4, 2)

    class FakeDate(date):
        @classmethod
        def today(cls):
            return today

    monkeypatch.setattr("Application.use_cases.get_admin_chart_data.date", FakeDate)

    spec = uuid4()
    repo = FakeRepo(
        [
            _appointment(today, spec, AppointmentStatus.COMPLETED, PaymentStatus.PAID, 120000),
            _appointment(today, spec, AppointmentStatus.COMPLETED, PaymentStatus.PAID, 80000),
            _appointment(today, spec, AppointmentStatus.COMPLETED, PaymentStatus.UNPAID, 400000),
        ]
    )

    use_case = GetAdminChartDataUseCase(appointment_repo=repo)
    result = await use_case.execute(range_type="week", metric="revenue")

    data = result["data"]
    assert data["metric"] == "revenue"
    assert data["total"] == 200000
    assert data["peak_day"]["date"] == str(today)
    assert data["peak_day"]["value"] == 200000
