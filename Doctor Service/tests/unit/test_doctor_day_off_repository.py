"""Unit tests for DoctorDayOffRepository."""
import pytest
from datetime import date
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.repositories.day_off_repository import DayOffRepository


@pytest.mark.asyncio
class TestDayOffRepository:
    """Test suite for DayOffRepository methods."""

    @pytest.fixture
    def session(self):
        """Mock AsyncSession."""
        return AsyncMock(spec=AsyncSession)

    @pytest.fixture
    def repository(self, session):
        """Create repository instance."""
        return DayOffRepository(session)

    @pytest.fixture
    def doctor_id(self):
        """Sample doctor ID."""
        return uuid4()

    # ====== CREATE TESTS ======

    async def test_create_day_off_without_reason(self, repository, session, doctor_id):
        """Test creating day-off record without reason."""
        # Arrange
        off_date = date(2026, 4, 15)

        session.add = MagicMock()
        session.flush = AsyncMock()

        # Act
        result = await repository.create(doctor_id, off_date, reason=None)

        # Assert
        assert result is not None
        session.add.assert_called_once()
        session.flush.assert_called_once()

    async def test_create_day_off_with_reason(self, repository, session, doctor_id):
        """Test creating day-off record with reason."""
        # Arrange
        off_date = date(2026, 4, 15)
        reason = "Medical appointment"

        session.add = MagicMock()
        session.flush = AsyncMock()

        # Act
        result = await repository.create(doctor_id, off_date, reason=reason)

        # Assert
        assert result is not None
        session.add.assert_called_once()
        session.flush.assert_called_once()

    # ====== DELETE TESTS ======

    async def test_delete_day_off_removes_record(self, repository, session, doctor_id):
        """Test deleting day-off record."""
        # Arrange
        off_date = date(2026, 4, 15)
        session.execute = AsyncMock()
        session.flush = AsyncMock()

        # Act
        result = await repository.delete(doctor_id, off_date)

        # Assert
        assert result is True
        session.execute.assert_called_once()
        session.flush.assert_called_once()

    async def test_delete_day_off_with_invalid_date(self, repository, session, doctor_id):
        """Test deleting non-existent day-off (still succeeds)."""
        # Arrange
        off_date = date(2026, 12, 31)
        session.execute = AsyncMock()
        session.flush = AsyncMock()

        # Act
        result = await repository.delete(doctor_id, off_date)

        # Assert
        assert result is True
        session.execute.assert_called_once()

    # ====== IS DAY OFF TESTS ======

    async def test_is_day_off_returns_true_when_exists(self, repository, session, doctor_id):
        """Test is_day_off returns True when day-off record exists."""
        # Arrange
        off_date = date(2026, 4, 15)
        existing_model = MagicMock(spec=DoctorDayOffModel)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing_model
        session.execute = AsyncMock(return_value=mock_result)

        # Act
        result = await repository.is_day_off(doctor_id, off_date)

        # Assert
        assert result is True
        session.execute.assert_called_once()

    async def test_is_day_off_returns_false_when_not_exists(self, repository, session, doctor_id):
        """Test is_day_off returns False when no day-off record."""
        # Arrange
        off_date = date(2026, 4, 15)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=mock_result)

        # Act
        result = await repository.is_day_off(doctor_id, off_date)

        # Assert
        assert result is False

    async def test_is_day_off_for_multiple_dates(self, repository, session, doctor_id):
        """Test checking multiple dates for day-off status."""
        # Arrange
        dates_and_expected = [
            (date(2026, 4, 13), False),
            (date(2026, 4, 14), True),
            (date(2026, 4, 15), False),
        ]

        # Act & Assert
        for check_date, expected in dates_and_expected:
            mock_execute = MagicMock()
            if expected:
                mock_execute.scalar_one_or_none.return_value = MagicMock()
            else:
                mock_execute.scalar_one_or_none.return_value = None
            session.execute = AsyncMock(return_value=mock_execute)

            result = await repository.is_day_off(doctor_id, check_date)
            assert result == expected
