import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock
from infrastructure.repositories.vitals_repository import VitalsRepository
from infrastructure.database.models import PatientProfileModel, PatientVitalsModel

@pytest.mark.asyncio
async def test_get_profile_id_success():
    session = AsyncMock()
    repo = VitalsRepository(session)
    user_id = uuid.uuid4()
    
    mock_result = MagicMock()
    mock_profile = MagicMock(spec=PatientProfileModel)
    mock_profile.id = uuid.uuid4()
    mock_result.scalar_one_or_none.return_value = mock_profile
    session.execute.return_value = mock_result
    
    pid = await repo._get_profile_id(user_id)
    assert pid == mock_profile.id
    session.execute.assert_called_once()

@pytest.mark.asyncio
async def test_create_vitals_success():
    session = AsyncMock()
    repo = VitalsRepository(session)
    user_id = uuid.uuid4()
    profile_id = uuid.uuid4()
    
    # Mock _get_profile_id internal call result via session.execute
    mock_result = MagicMock()
    mock_profile = MagicMock(spec=PatientProfileModel)
    mock_profile.id = profile_id
    mock_result.scalar_one_or_none.return_value = mock_profile
    session.execute.return_value = mock_result
    
    await repo.create(user_id, uuid.uuid4(), {"weight_kg": 70.0, "height_cm": 175.0})
    session.add.assert_called_once()
    session.flush.assert_called_once()

@pytest.mark.asyncio
async def test_create_vitals_profile_not_found():
    session = AsyncMock()
    repo = VitalsRepository(session)
    
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    session.execute.return_value = mock_result
    
    with pytest.raises(ValueError, match="Patient profile not found"):
        await repo.create(uuid.uuid4(), uuid.uuid4(), {})

@pytest.mark.asyncio
async def test_get_latest_vitals_none():
    session = AsyncMock()
    repo = VitalsRepository(session)
    
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    session.execute.return_value = mock_result
    
    res = await repo.get_latest(uuid.uuid4())
    assert res is None
