from uuid import uuid4

import pytest
from fastapi import HTTPException

from Domain.entities.patient_health_background import PatientHealthBackground
from Domain.entities.patient_profile import PatientProfile
from presentation import dependencies


def test_patient_dependencies_repositories_and_publisher_smoke():
    session = object()
    assert dependencies.get_profile_repo(session) is not None
    assert dependencies.get_health_repo(session) is not None


def test_get_current_user_id_valid():
    uid = uuid4()
    assert dependencies.get_current_user_id(str(uid)) == uid


def test_get_current_user_id_missing_raises_401():
    with pytest.raises(HTTPException) as exc:
        dependencies.get_current_user_id(None)
    assert exc.value.status_code == 401


def test_get_current_user_id_invalid_raises_401():
    with pytest.raises(HTTPException) as exc:
        dependencies.get_current_user_id("not-a-uuid")
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_patient_domain_entities_update_helpers():
    profile = PatientProfile(user_id=uuid4())
    profile.update_profile(full_name="Alice")
    assert profile.full_name == "Alice"

    health = PatientHealthBackground(patient_id=profile.id)
    health.update_background(height_cm=170)
    assert health.height_cm == 170
