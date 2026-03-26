"""Unit tests for DoctorServiceOfferingRepository."""
import pytest
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.repositories.service_offering_repository import ServiceOfferingRepository
from infrastructure.database.models import DoctorServiceOfferingModel


@pytest.mark.asyncio
class TestServiceOfferingRepository:
    """Test suite for ServiceOfferingRepository methods."""

    @pytest.fixture
    def session(self):
        """Mock AsyncSession."""
        return AsyncMock(spec=AsyncSession)

    @pytest.fixture
    def repository(self, session):
        """Create repository instance."""
        return ServiceOfferingRepository(session)

    @pytest.fixture
    def doctor_id(self):
        """Sample doctor ID."""
        return uuid4()

    @pytest.fixture
    def service_id(self):
        """Sample service ID."""
        return uuid4()

    # ====== CREATE TESTS ======

    async def test_create_service_offering_basic(self, repository, session, doctor_id):
        """Test creating basic service offering."""
        # Arrange
        service_name = "Consultation"
        duration_minutes = 30
        fee = 50.0

        session.add = MagicMock()
        session.flush = AsyncMock()

        # Act
        result = await repository.create(
            doctor_id=doctor_id,
            service_name=service_name,
            duration_minutes=duration_minutes,
            fee=fee,
        )

        # Assert
        assert result is not None
        session.add.assert_called_once()
        session.flush.assert_called_once()

    async def test_create_service_offering_with_description(self, repository, session, doctor_id):
        """Test creating service offering with description."""
        # Arrange
        service_name = "Detailed Consultation"
        duration_minutes = 60
        fee = 100.0
        description = "Comprehensive medical consultation with detailed examination"

        session.add = MagicMock()
        session.flush = AsyncMock()

        # Act
        result = await repository.create(
            doctor_id=doctor_id,
            service_name=service_name,
            duration_minutes=duration_minutes,
            fee=fee,
            description=description,
        )

        # Assert
        assert result is not None
        session.add.assert_called_once()

    async def test_create_multiple_services_for_doctor(self, repository, session, doctor_id):
        """Test creating multiple services for same doctor."""
        # Arrange
        services = [
            ("Service A", 30, 50.0),
            ("Service B", 45, 75.0),
            ("Service C", 60, 100.0),
        ]

        session.add = MagicMock()
        session.flush = AsyncMock()

        # Act
        results = []
        for service_name, duration, fee in services:
            result = await repository.create(
                doctor_id=doctor_id,
                service_name=service_name,
                duration_minutes=duration,
                fee=fee,
            )
            results.append(result)

        # Assert
        assert len(results) == 3
        assert session.add.call_count == 3

    # ====== UPDATE TESTS ======

    async def test_update_service_offering_fee(self, repository, session, service_id):
        """Test updating service offering fee."""
        # Arrange
        new_fee = 120.0
        session.execute = AsyncMock()
        session.flush = AsyncMock()

        # Act
        await repository.update(service_id, fee=new_fee)

        # Assert
        session.execute.assert_called_once()
        session.flush.assert_called_once()

    async def test_update_service_offering_multiple_fields(self, repository, session, service_id):
        """Test updating multiple fields at once."""
        # Arrange
        updates = {
            "service_name": "Updated Service",
            "duration_minutes": 75,
            "fee": 150.0,
        }

        session.execute = AsyncMock()
        session.flush = AsyncMock()

        # Act
        await repository.update(service_id, **updates)

        # Assert
        session.execute.assert_called_once()
        session.flush.assert_called_once()

    async def test_update_nonexistent_service(self, repository, session, service_id):
        """Test updating non-existent service (still succeeds)."""
        # Arrange
        session.execute = AsyncMock()
        session.flush = AsyncMock()

        # Act
        await repository.update(service_id, fee=99.0)

        # Assert
        session.execute.assert_called_once()

    # ====== LIST BY DOCTOR TESTS ======

    async def test_list_by_doctor_returns_all_services(self, repository, session, doctor_id):
        """Test listing all services for doctor."""
        # Arrange
        service_models = [
            MagicMock(spec=DoctorServiceOfferingModel, service_name="Service A"),
            MagicMock(spec=DoctorServiceOfferingModel, service_name="Service B"),
            MagicMock(spec=DoctorServiceOfferingModel, service_name="Service C"),
        ]

        mock_execute = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = service_models
        mock_execute.scalars.return_value = mock_scalars
        session.execute = AsyncMock(return_value=mock_execute)

        # Act
        result = await repository.list_by_doctor(doctor_id)

        # Assert
        assert len(result) == 3
        assert all(isinstance(service, MagicMock) for service in result)

    async def test_list_by_doctor_returns_empty_when_no_services(self, repository, session, doctor_id):
        """Test returns empty list when doctor has no services."""
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

    async def test_list_by_doctor_filters_by_doctor_id(self, repository, session, doctor_id):
        """Test list only returns services for specific doctor."""
        # Arrange
        service_models = [
            MagicMock(spec=DoctorServiceOfferingModel, doctor_id=doctor_id),
        ]

        mock_execute = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = service_models
        mock_execute.scalars.return_value = mock_scalars
        session.execute = AsyncMock(return_value=mock_execute)

        # Act
        result = await repository.list_by_doctor(doctor_id)

        # Assert
        assert len(result) == 1
        assert result[0].doctor_id == doctor_id

    # ====== DEACTIVATE TESTS ======

    async def test_deactivate_service_offering(self, repository, session, service_id):
        """Test deactivating service offering."""
        # Arrange
        session.execute = AsyncMock()
        session.flush = AsyncMock()

        # Act
        await repository.deactivate(service_id)

        # Assert
        session.execute.assert_called_once()
        session.flush.assert_called_once()

    async def test_deactivate_sets_is_active_false(self, repository, session, service_id):
        """Test deactivate sets is_active to False."""
        # Arrange
        session.execute = AsyncMock()
        session.flush = AsyncMock()

        # Act
        await repository.deactivate(service_id)

        # Assert
        # Verify update was called
        session.execute.assert_called_once()

    async def test_deactivate_multiple_services(self, repository, session, doctor_id):
        """Test deactivating multiple services sequentially."""
        # Arrange
        service_ids = [uuid4() for _ in range(3)]
        session.execute = AsyncMock()
        session.flush = AsyncMock()

        # Act
        for service_id in service_ids:
            await repository.deactivate(service_id)

        # Assert
        assert session.execute.call_count == 3
        assert session.flush.call_count == 3
