from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from Application.use_cases.get_health_summary import GetHealthSummaryUseCase
from Application.use_cases.manage_vitals import GetLatestVitalsUseCase, GetVitalsHistoryUseCase, RecordVitalsUseCase
from Domain.entities.patient_health_background import BloodType, PatientHealthBackground
from Domain.entities.patient_profile import PatientProfile


@pytest.mark.asyncio
async def test_record_vitals_initializes_profile_then_creates_vitals():
    patient_id = uuid4()
    recorder_id = uuid4()

    init_use_case = SimpleNamespace(execute=AsyncMock())
    vitals_repo = SimpleNamespace(create=AsyncMock(return_value={"ok": True}))

    use_case = RecordVitalsUseCase(vitals_repo=vitals_repo, initialize_use_case=init_use_case)
    result = await use_case.execute(
        patient_id=patient_id,
        recorded_by=recorder_id,
        height_cm=170,
        weight_kg=65.5,
        heart_rate=72,
    )

    assert result == {"ok": True}
    init_use_case.execute.assert_awaited_once_with(patient_id)
    vitals_repo.create.assert_awaited_once_with(
        patient_id,
        recorder_id,
        {"height_cm": 170, "weight_kg": 65.5, "heart_rate": 72},
    )


@pytest.mark.asyncio
async def test_get_latest_vitals_returns_none_for_empty_state():
    patient_id = uuid4()
    vitals_repo = SimpleNamespace(get_latest=AsyncMock(return_value=None))

    use_case = GetLatestVitalsUseCase(vitals_repo=vitals_repo)
    result = await use_case.execute(patient_id)

    assert result is None
    vitals_repo.get_latest.assert_awaited_once_with(patient_id)


@pytest.mark.asyncio
async def test_get_latest_vitals_returns_existing_record_and_initializes_profile():
    patient_id = uuid4()
    existing = SimpleNamespace(id=uuid4(), weight_kg=70)

    init_use_case = SimpleNamespace(execute=AsyncMock())
    vitals_repo = SimpleNamespace(get_latest=AsyncMock(return_value=existing))

    use_case = GetLatestVitalsUseCase(vitals_repo=vitals_repo, initialize_use_case=init_use_case)
    result = await use_case.execute(patient_id)

    assert result is existing
    init_use_case.execute.assert_awaited_once_with(patient_id)
    vitals_repo.get_latest.assert_awaited_once_with(patient_id)


@pytest.mark.asyncio
async def test_get_vitals_history_applies_pagination_offset_and_limit():
    patient_id = uuid4()
    sample_rows = [SimpleNamespace(id=uuid4())]
    vitals_repo = SimpleNamespace(list_by_patient=AsyncMock(return_value=sample_rows))

    use_case = GetVitalsHistoryUseCase(vitals_repo=vitals_repo)
    result = await use_case.execute(patient_id=patient_id, page=3, limit=10)

    assert result == sample_rows
    vitals_repo.list_by_patient.assert_awaited_once_with(patient_id, 10, 20)


@pytest.mark.asyncio
async def test_get_health_summary_aggregates_profile_and_health_background():
    user_id = uuid4()
    profile = PatientProfile(user_id=user_id)
    health = PatientHealthBackground(
        patient_id=profile.id,
        blood_type=BloodType.A,
        allergies=["dust"],
        chronic_conditions=["asthma"],
    )
    setattr(health, "medical_conditions", ["asthma"])
    setattr(health, "current_medications", ["inhaler"])

    profile_repo = SimpleNamespace(
        get_by_user_id=AsyncMock(return_value=profile),
        create=AsyncMock(),
    )
    health_repo = SimpleNamespace(get_by_patient_id=AsyncMock(return_value=health))

    use_case = GetHealthSummaryUseCase(profile_repo=profile_repo, health_repo=health_repo)
    result = await use_case.execute(user_id)

    assert result == {
        "user_id": str(user_id),
        "blood_type": BloodType.A,
        "allergies": ["dust"],
        "medical_conditions": ["asthma"],
        "current_medications": ["inhaler"],
    }
    profile_repo.get_by_user_id.assert_awaited_once_with(user_id)
    health_repo.get_by_patient_id.assert_awaited_once_with(profile.id)


@pytest.mark.asyncio
async def test_get_health_summary_returns_defaults_when_no_background_exists():
    user_id = uuid4()
    profile = PatientProfile(user_id=user_id)

    profile_repo = SimpleNamespace(
        get_by_user_id=AsyncMock(return_value=profile),
        create=AsyncMock(),
    )
    health_repo = SimpleNamespace(get_by_patient_id=AsyncMock(return_value=None))

    use_case = GetHealthSummaryUseCase(profile_repo=profile_repo, health_repo=health_repo)
    result = await use_case.execute(user_id)

    assert result["blood_type"] is None
    assert result["allergies"] == []
    assert result["medical_conditions"] == []
    assert result["current_medications"] == []
