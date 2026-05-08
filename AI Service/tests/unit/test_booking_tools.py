import pytest

from infrastructure.llm.booking_tools import fn_check_availability


class _FakeClientUnsupported:
    _SUPPORTED_DEPARTMENTS = ("Cardiology", "General Medicine")

    def resolve_department_to_specialty(self, department: str):
        return None


class _FakeClientNoDoctors:
    _SUPPORTED_DEPARTMENTS = ("Cardiology",)

    def resolve_department_to_specialty(self, department: str):
        return "Cardiology"

    async def get_doctors_by_specialty(self, specialty_name: str):
        return []


class _FakeClientNoSlots:
    _SUPPORTED_DEPARTMENTS = ("Cardiology",)

    def resolve_department_to_specialty(self, department: str):
        return "Cardiology"

    async def get_doctors_by_specialty(self, specialty_name: str):
        return [{"user_id": "d1", "specialty_id": "s1", "full_name": "Dr. A"}]

    async def check_availability_by_department(self, department: str, appointment_date: str):
        return []


@pytest.mark.asyncio
async def test_check_availability_unsupported_department(monkeypatch):
    monkeypatch.setattr(
        "infrastructure.llm.booking_tools.AppointmentServiceClient",
        _FakeClientUnsupported,
    )
    result = await fn_check_availability("Respiratory", "2026-05-07")
    assert result["status"] == "unsupported_department"


@pytest.mark.asyncio
async def test_check_availability_no_doctors(monkeypatch):
    monkeypatch.setattr(
        "infrastructure.llm.booking_tools.AppointmentServiceClient",
        _FakeClientNoDoctors,
    )
    result = await fn_check_availability("Cardiology", "2026-05-07")
    assert result["status"] == "no_doctors"


@pytest.mark.asyncio
async def test_check_availability_no_slots_for_date(monkeypatch):
    monkeypatch.setattr(
        "infrastructure.llm.booking_tools.AppointmentServiceClient",
        _FakeClientNoSlots,
    )
    result = await fn_check_availability("Cardiology", "2026-05-07")
    assert result["status"] == "no_slots_for_date"
