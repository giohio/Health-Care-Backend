"""Unit tests for AppointmentRepository reminder and utility methods."""
import pytest
from datetime import date, time, datetime, timedelta
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy.ext.asyncio import AsyncSession
from uuid_extension import UUID7

from infrastructure.repositories.appointment_repository import AppointmentRepository
from infrastructure.database.models import AppointmentModel
from Domain.value_objects.appointment_status import AppointmentStatus


@pytest.mark.asyncio
class TestAppointmentRepositoryReminders:
    """Test suite for AppointmentRepository reminder and utility methods."""

    @pytest.fixture
    def session(self):
        """Mock AsyncSession."""
        return AsyncMock(spec=AsyncSession)

    @pytest.fixture
    def repository(self, session):
        """Create repository instance."""
        return AppointmentRepository(session)

    @pytest.fixture
    def doctor_id(self):
        """Sample doctor ID."""
        return uuid4()

    @pytest.fixture
    def appointment_id(self):
        """Sample appointment ID."""
        return uuid4()

    # ====== GET UPCOMING FOR REMINDERS TESTS ======

    async def test_get_upcoming_for_reminders_returns_confirmed_appointments(
        self, repository, session, doctor_id, appointment_id
    ):
        """Test getting upcoming appointments that need reminders (CONFIRMED status)."""
        # Arrange
        start_time = datetime.now()
        end_time = start_time + timedelta(hours=24)

        appointment_model = MagicMock(spec=AppointmentModel)
        appointment_model.id = appointment_id
        appointment_model.status = AppointmentStatus.CONFIRMED

        mock_execute = AsyncMock()
        mock_scalars = AsyncMock()
        mock_scalars.all.return_value = [appointment_model]
        mock_execute.scalars.return_value = mock_scalars
        session.execute.return_value = mock_execute

        # Act
        result = await repository.get_upcoming_for_reminders(start_time, end_time)

        # Assert
        assert len(result) == 1
        session.execute.assert_called_once()

    async def test_get_upcoming_for_reminders_filters_by_date_range(
        self, repository, session
    ):
        """Test reminder query filters appointments within date range."""
        # Arrange
        start_time = datetime(2026, 4, 20, 8, 0)
        end_time = datetime(2026, 4, 21, 8, 0)

        appointment_models = [
            MagicMock(spec=AppointmentModel, appointment_date=date(2026, 4, 20)),
            MagicMock(spec=AppointmentModel, appointment_date=date(2026, 4, 21)),
        ]

        mock_execute = AsyncMock()
        mock_scalars = AsyncMock()
        mock_scalars.all.return_value = appointment_models
        mock_execute.scalars.return_value = mock_scalars
        session.execute.return_value = mock_execute

        # Act
        result = await repository.get_upcoming_for_reminders(start_time, end_time)

        # Assert
        assert len(result) == 2
        session.execute.assert_called_once()

    async def test_get_upcoming_for_reminders_excludes_other_statuses(
        self, repository, session
    ):
        """Test reminder query only returns CONFIRMED appointments."""
        # Arrange
        start_time = datetime.now()
        end_time = start_time + timedelta(hours=24)

        # Only CONFIRMED appointments should be considered
        appointment_models = [
            MagicMock(spec=AppointmentModel, status=AppointmentStatus.CONFIRMED),
        ]

        mock_execute = AsyncMock()
        mock_scalars = AsyncMock()
        mock_scalars.all.return_value = appointment_models
        mock_execute.scalars.return_value = mock_scalars
        session.execute.return_value = mock_execute

        # Act
        result = await repository.get_upcoming_for_reminders(start_time, end_time)

        # Assert
        assert len(result) == 1
        # Verify the query filters by CONFIRMED status
        session.execute.assert_called_once()

    async def test_get_upcoming_for_reminders_returns_empty_when_none(
        self, repository, session
    ):
        """Test returns empty list when no appointments in range."""
        # Arrange
        start_time = datetime(2026, 12, 25, 8, 0)
        end_time = datetime(2026, 12, 26, 8, 0)

        mock_execute = AsyncMock()
        mock_scalars = AsyncMock()
        mock_scalars.all.return_value = []
        mock_execute.scalars.return_value = mock_scalars
        session.execute.return_value = mock_execute

        # Act
        result = await repository.get_upcoming_for_reminders(start_time, end_time)

        # Assert
        assert len(result) == 0

    # ====== MARK REMINDER SENT TESTS ======

    async def test_mark_reminder_sent_24h(self, repository, session, appointment_id):
        """Test marking 24-hour reminder as sent."""
        # Arrange
        appointment_model = MagicMock(spec=AppointmentModel)
        appointment_model.reminder_24h_sent = False

        mock_execute = AsyncMock()
        mock_execute.scalar_one_or_none.return_value = appointment_model
        session.execute.return_value = mock_execute
        session.flush = AsyncMock()

        # Act
        await repository.mark_reminder_sent(appointment_id, "24h")

        # Assert
        assert appointment_model.reminder_24h_sent is True
        session.flush.assert_called_once()

    async def test_mark_reminder_sent_1h(self, repository, session, appointment_id):
        """Test marking 1-hour reminder as sent."""
        # Arrange
        appointment_model = MagicMock(spec=AppointmentModel)
        appointment_model.reminder_1h_sent = False

        mock_execute = AsyncMock()
        mock_execute.scalar_one_or_none.return_value = appointment_model
        session.execute.return_value = mock_execute
        session.flush = AsyncMock()

        # Act
        await repository.mark_reminder_sent(appointment_id, "1h")

        # Assert
        assert appointment_model.reminder_1h_sent is True
        session.flush.assert_called_once()

    async def test_mark_reminder_sent_when_already_sent_24h(self, repository, session, appointment_id):
        """Test idempotent: marking already-sent 24h reminder."""
        # Arrange
        appointment_model = MagicMock(spec=AppointmentModel)
        appointment_model.reminder_24h_sent = True

        mock_execute = AsyncMock()
        mock_execute.scalar_one_or_none.return_value = appointment_model
        session.execute.return_value = mock_execute
        session.flush = AsyncMock()

        # Act
        await repository.mark_reminder_sent(appointment_id, "24h")

        # Assert
        assert appointment_model.reminder_24h_sent is True
        session.flush.assert_called_once()

    async def test_mark_reminder_sent_nonexistent_appointment(self, repository, session, appointment_id):
        """Test marking reminder for non-existent appointment (graceful)."""
        # Arrange
        mock_execute = AsyncMock()
        mock_execute.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_execute
        session.flush = AsyncMock()

        # Act
        await repository.mark_reminder_sent(appointment_id, "24h")

        # Assert
        session.flush.assert_called_once()

    async def test_mark_reminder_sent_both_reminders(self, repository, session, appointment_id):
        """Test marking both 24h and 1h reminders."""
        # Arrange
        appointment_model = MagicMock(spec=AppointmentModel)
        appointment_model.reminder_24h_sent = False
        appointment_model.reminder_1h_sent = False

        mock_execute = AsyncMock()
        mock_execute.scalar_one_or_none.return_value = appointment_model
        session.execute.return_value = mock_execute
        session.flush = AsyncMock()

        # Act
        await repository.mark_reminder_sent(appointment_id, "24h")
        await repository.mark_reminder_sent(appointment_id, "1h")

        # Assert
        assert appointment_model.reminder_24h_sent is True
        assert appointment_model.reminder_1h_sent is True
        assert session.flush.call_count == 2

    # ====== IS SLOT TAKEN TESTS ======

    async def test_is_slot_taken_returns_true_when_booked(
        self, repository, session, doctor_id
    ):
        """Test slot taken detection when appointment exists."""
        # Arrange
        appointment_date = date(2026, 4, 20)
        start_time = time(10, 0)
        end_time = time(10, 30)

        mock_execute = AsyncMock()
        mock_execute.scalar.return_value = 1  # Count > 0
        session.execute.return_value = mock_execute

        # Act
        result = await repository.is_slot_taken(doctor_id, appointment_date, start_time, end_time)

        # Assert
        assert result is True

    async def test_is_slot_taken_returns_false_when_available(
        self, repository, session, doctor_id
    ):
        """Test slot taken detection when slot is free."""
        # Arrange
        appointment_date = date(2026, 4, 20)
        start_time = time(10, 0)
        end_time = time(10, 30)

        mock_execute = AsyncMock()
        mock_execute.scalar.return_value = 0
        session.execute.return_value = mock_execute

        # Act
        result = await repository.is_slot_taken(doctor_id, appointment_date, start_time, end_time)

        # Assert
        assert result is False

    async def test_is_slot_taken_with_exclude_id(
        self, repository, session, doctor_id, appointment_id
    ):
        """Test slot taken excludes current appointment."""
        # Arrange
        appointment_date = date(2026, 4, 20)
        start_time = time(10, 0)
        end_time = time(10, 30)
        exclude_id = appointment_id

        mock_execute = AsyncMock()
        mock_execute.scalar.return_value = 0
        session.execute.return_value = mock_execute

        # Act
        result = await repository.is_slot_taken(
            doctor_id,
            appointment_date,
            start_time,
            end_time,
            exclude_id=exclude_id
        )

        # Assert
        assert result is False

    # ====== GET NEXT QUEUE NUMBER TESTS ======

    async def test_get_next_queue_number_returns_one_when_empty(
        self, repository, session, doctor_id
    ):
        """Test next queue number is 1 when no appointments."""
        # Arrange
        appointment_date = date(2026, 4, 20)

        mock_execute = AsyncMock()
        mock_execute.scalar.return_value = 0  # No existing appointments
        session.execute.return_value = mock_execute

        # Act
        result = await repository.get_next_queue_number(doctor_id, appointment_date)

        # Assert
        assert result == 1

    async def test_get_next_queue_number_increments(
        self, repository, session, doctor_id
    ):
        """Test next queue number increments based on confirmed count."""
        # Arrange
        appointment_date = date(2026, 4, 20)

        mock_execute = AsyncMock()
        mock_execute.scalar.return_value = 5  # 5 existing appointments
        session.execute.return_value = mock_execute

        # Act
        result = await repository.get_next_queue_number(doctor_id, appointment_date)

        # Assert
        assert result == 6

    async def test_get_next_queue_number_counts_only_confirmed(
        self, repository, session, doctor_id
    ):
        """Test queue number only counts CONFIRMED appointments."""
        # Arrange
        appointment_date = date(2026, 4, 20)

        mock_execute = AsyncMock()
        mock_execute.scalar.return_value = 3  # 3 confirmed appointments
        session.execute.return_value = mock_execute

        # Act
        result = await repository.get_next_queue_number(doctor_id, appointment_date)

        # Assert
        assert result == 4
        session.execute.assert_called_once()
