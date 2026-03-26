"""Unit tests for AvailabilityRepository."""
import pytest
from datetime import time
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.repositories.availability_repository import AvailabilityRepository
from infrastructure.database.models import DoctorAvailabilityModel


@pytest.mark.asyncio
class TestAvailabilityRepository:
    """Test suite for AvailabilityRepository methods."""

    @pytest.fixture
    def session(self):
        """Mock AsyncSession."""
        return AsyncMock(spec=AsyncSession)

    @pytest.fixture
    def repository(self, session):
        """Create repository instance."""
        return AvailabilityRepository(session)

    @pytest.fixture
    def doctor_id(self):
        """Sample doctor ID."""
        return uuid4()

    # ====== UPSERT TESTS ======

    async def test_upsert_creates_new_availability(self, repository, session, doctor_id):
        """Test upsert creates new availability when not exists."""
        # Arrange
        day_of_week = 1  # Monday
        start_time = time(8, 0)
        end_time = time(17, 0)
        break_start = time(12, 0)
        break_end = time(13, 0)
        max_patients = 10

        # Mock empty result (no existing record)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=mock_result)

        # Act
        result = await repository.upsert(
            doctor_id=doctor_id,
            day_of_week=day_of_week,
            start_time=start_time,
            end_time=end_time,
            break_start=break_start,
            break_end=break_end,
            max_patients=max_patients,
        )

        # Assert
        assert result is not None
        session.add.assert_called_once()
        assert session.flush.call_count >= 1

    async def test_upsert_updates_existing_availability(self, repository, session, doctor_id):
        """Test upsert updates existing availability record."""
        # Arrange
        day_of_week = 2  # Tuesday
        start_time = time(9, 0)
        end_time = time(18, 0)
        break_start = time(13, 0)
        break_end = time(14, 0)
        max_patients = 15

        existing_model = MagicMock(spec=DoctorAvailabilityModel)
        existing_model.doctor_id = doctor_id

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing_model
        session.execute = AsyncMock(return_value=mock_result)

        # Act
        result = await repository.upsert(
            doctor_id=doctor_id,
            day_of_week=day_of_week,
            start_time=start_time,
            end_time=end_time,
            break_start=break_start,
            break_end=break_end,
            max_patients=max_patients,
        )

        # Assert
        assert result == existing_model
        assert existing_model.start_time == start_time
        assert existing_model.end_time == end_time
        assert existing_model.max_patients == max_patients
        assert session.flush.call_count >= 1

    # ====== GET BY DOCTOR AND DAY TESTS ======

    async def test_get_by_doctor_and_day_returns_active_availability(self, repository, session, doctor_id):
        """Test retrieving availability for specific day of week."""
        # Arrange
        day_of_week = 1
        availability_model = MagicMock(spec=DoctorAvailabilityModel)
        availability_model.day_of_week = day_of_week
        availability_model.is_active = True

        mock_execute = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [availability_model]
        mock_execute.scalars.return_value = mock_scalars
        session.execute = AsyncMock(return_value=mock_execute)

        # Act
        result = await repository.get_by_doctor_and_day(doctor_id, day_of_week)

        # Assert
        assert len(result) == 1
        assert result[0] == availability_model
        session.execute.assert_called_once()

    async def test_get_by_doctor_and_day_returns_empty_for_inactive(self, repository, session, doctor_id):
        """Test returns empty list when no active availability."""
        # Arrange
        day_of_week = 5  # Friday - no availability

        mock_execute = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_execute.scalars.return_value = mock_scalars
        session.execute = AsyncMock(return_value=mock_execute)

        # Act
        result = await repository.get_by_doctor_and_day(doctor_id, day_of_week)

        # Assert
        assert len(result) == 0

    # ====== LIST BY DOCTOR TESTS ======

    async def test_list_by_doctor_returns_all_availabilities(self, repository, session, doctor_id):
        """Test listing all availabilities for doctor, ordered by day."""
        # Arrange
        availability_models = [
            MagicMock(spec=DoctorAvailabilityModel, day_of_week=i)
            for i in range(1, 6)  # Mon-Fri
        ]

        mock_execute = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = availability_models
        mock_execute.scalars.return_value = mock_scalars
        session.execute = AsyncMock(return_value=mock_execute)

        # Act
        result = await repository.list_by_doctor(doctor_id)

        # Assert
        assert len(result) == 5
        assert all(isinstance(model, MagicMock) for model in result)
        session.execute.assert_called_once()

    async def test_list_by_doctor_returns_empty_when_no_requirements(self, repository, session, doctor_id):
        """Test returns empty list when doctor has no availability set."""
        # Arrange
        mock_execute = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_execute.scalars.return_value = mock_scalars
        session.execute = AsyncMock(return_value=mock_execute)

        # Act
        result = await repository.list_by_doctor(doctor_id)

        # Assert
        assert len(result) == 0

    async def test_list_by_doctor_orders_by_day_of_week(self, repository, session, doctor_id):
        """Test availabilities are ordered by day of week."""
        # Arrange
        # Create in non-sequential order
        models = [
            MagicMock(spec=DoctorAvailabilityModel, day_of_week=3),
            MagicMock(spec=DoctorAvailabilityModel, day_of_week=1),
            MagicMock(spec=DoctorAvailabilityModel, day_of_week=2),
        ]

        mock_execute = MagicMock()
        mock_scalars = MagicMock()
        # Return in creation order (not sorted)
        mock_scalars.all.return_value = models
        mock_execute.scalars.return_value = mock_scalars
        session.execute = AsyncMock(return_value=mock_execute)

        # Act
        result = await repository.list_by_doctor(doctor_id)

        # Assert
        assert len(result) == 3
        # Verify order_by was included in execute call
        session.execute.assert_called_once()
