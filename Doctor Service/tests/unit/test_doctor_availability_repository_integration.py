"""Unit tests for AvailabilityRepository using AsyncMock."""
import pytest
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import time
from uuid import uuid4

from infrastructure.repositories.availability_repository import AvailabilityRepository
from infrastructure.database.models import DoctorAvailabilityModel


@pytest.fixture
def mock_session():
    """Create a mock async session with sync add."""
    session = MagicMock(spec=AsyncSession)
    session.add = MagicMock()
    session.execute = AsyncMock()
    session.flush = AsyncMock()
    return session


@pytest.mark.asyncio
class TestAvailabilityRepositoryUnit:
    """Unit tests for AvailabilityRepository with AsyncMock."""

    async def test_upsert_creates_new_availability(self, mock_session):
        """Test upsert creates new availability when not exists."""
        # Arrange
        repo = AvailabilityRepository(mock_session)
        doctor_id = uuid4()
        day_of_week = 1
        start_time = time(8, 0)
        end_time = time(17, 0)

        # Mock result of execute to return None for scalar_one_or_none
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        # Act
        result = await repo.upsert(
            doctor_id=doctor_id,
            day_of_week=day_of_week,
            start_time=start_time,
            end_time=end_time,
            break_start=time(12, 0),
            break_end=time(13, 0),
            max_patients=10
        )

        # Assert
        assert result is not None
        mock_session.add.assert_called_once()
        added_obj = mock_session.add.call_args[0][0]
        assert isinstance(added_obj, DoctorAvailabilityModel)
        assert added_obj.doctor_id == doctor_id

    async def test_upsert_updates_existing_availability(self, mock_session):
        """Test upsert updates existing availability record."""
        # Arrange
        repo = AvailabilityRepository(mock_session)
        doctor_id = uuid4()
        day_of_week = 1
        
        # Create an existing model instance
        existing_model = DoctorAvailabilityModel(
            doctor_id=doctor_id,
            day_of_week=day_of_week,
            start_time=time(8, 0),
            end_time=time(17, 0)
        )

        # Mock result of execute to return the existing record
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing_model
        mock_session.execute.return_value = mock_result

        # Act
        result = await repo.upsert(
            doctor_id=doctor_id,
            day_of_week=day_of_week,
            start_time=time(9, 0),
            end_time=time(18, 0),
            break_start=time(13, 0),
            break_end=time(14, 0),
            max_patients=15
        )

        # Assert
        assert result.start_time == time(9, 0)
        assert result.max_patients == 15
        # Update shouldn't call session.add again
        mock_session.add.assert_not_called()

    async def test_list_by_doctor_returns_availabilities(self, mock_session):
        """Test listing all availabilities for doctor."""
        # Arrange
        repo = AvailabilityRepository(mock_session)
        doctor_id = uuid4()

        # Mock result
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [
            DoctorAvailabilityModel(doctor_id=doctor_id, day_of_week=i) for i in range(1, 4)
        ]
        mock_session.execute.return_value = mock_result

        # Act
        results = await repo.list_by_doctor(doctor_id)

        # Assert
        assert len(results) == 3
        mock_session.execute.assert_called_once()

    async def test_get_by_doctor_and_day_returns_active_availability(self, mock_session):
        """Test retrieving availability for specific day."""
        # Arrange
        repo = AvailabilityRepository(mock_session)
        doctor_id = uuid4()
        day_of_week = 3

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [
            DoctorAvailabilityModel(doctor_id=doctor_id, day_of_week=day_of_week)
        ]
        mock_session.execute.return_value = mock_result

        # Act
        results = await repo.get_by_doctor_and_day(doctor_id, day_of_week)

        # Assert
        assert len(results) == 1
        assert results[0].day_of_week == day_of_week
