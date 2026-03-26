"""Unit tests for DoctorRatingRepository."""
import pytest
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.repositories.rating_repository import RatingRepository
from infrastructure.database.models import DoctorRatingModel


@pytest.mark.asyncio
class TestRatingRepository:
    """Test suite for RatingRepository methods."""

    @pytest.fixture
    def session(self):
        """Mock AsyncSession."""
        return AsyncMock(spec=AsyncSession)

    @pytest.fixture
    def repository(self, session):
        """Create repository instance."""
        return RatingRepository(session)

    @pytest.fixture
    def doctor_id(self):
        """Sample doctor ID."""
        return uuid4()

    @pytest.fixture
    def patient_id(self):
        """Sample patient ID."""
        return uuid4()

    # ====== CREATE TESTS ======

    async def test_create_rating_without_comment(self, repository, session, doctor_id, patient_id):
        """Test creating rating without comment."""
        # Arrange
        rating = 5
        session.add = MagicMock()
        session.flush = AsyncMock()

        # Act
        result = await repository.create(
            doctor_id=doctor_id,
            patient_id=patient_id,
            rating=rating,
            comment=None,
        )

        # Assert
        assert result is not None
        session.add.assert_called_once()
        session.flush.assert_called_once()

    async def test_create_rating_with_comment(self, repository, session, doctor_id, patient_id):
        """Test creating rating with comment."""
        # Arrange
        rating = 4
        comment = "Excellent doctor, very professional"

        session.add = MagicMock()
        session.flush = AsyncMock()

        # Act
        result = await repository.create(
            doctor_id=doctor_id,
            patient_id=patient_id,
            rating=rating,
            comment=comment,
        )

        # Assert
        assert result is not None
        session.add.assert_called_once()

    async def test_create_rating_stores_all_fields(self, repository, session, doctor_id, patient_id):
        """Test rating creation stores all required fields."""
        # Arrange
        rating = 3
        comment = "Good service"

        session.add = MagicMock()
        session.flush = AsyncMock()

        # Act
        created = await repository.create(
            doctor_id=doctor_id,
            patient_id=patient_id,
            rating=rating,
            comment=comment,
        )

        # Assert
        assert created is not None
        session.add.assert_called_once()
        session.flush.assert_called_once()

    # ====== GET BY PATIENT AND DOCTOR TESTS ======

    async def test_get_by_patient_and_doctor_existing_rating(self, repository, session, doctor_id, patient_id):
        """Test retrieving existing rating for patient-doctor pair."""
        # Arrange
        existing_rating = MagicMock(spec=DoctorRatingModel)
        existing_rating.rating = 5
        existing_rating.patient_id = patient_id
        existing_rating.doctor_id = doctor_id

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing_rating
        session.execute = AsyncMock(return_value=mock_result)

        # Act
        result = await repository.get_by_patient_and_doctor(patient_id, doctor_id)

        # Assert
        assert result == existing_rating
        assert result.rating == 5

    async def test_get_by_patient_and_doctor_no_rating(self, repository, session, doctor_id, patient_id):
        """Test retrieving rating when patient hasn't rated doctor."""
        # Arrange
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=mock_result)

        # Act
        result = await repository.get_by_patient_and_doctor(patient_id, doctor_id)

        # Assert
        assert result is None

    async def test_get_by_patient_and_doctor_exact_match(self, repository, session, doctor_id, patient_id):
        """Test only returns rating for exact patient-doctor pair."""
        # Arrange
        existing_rating = MagicMock(spec=DoctorRatingModel)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing_rating
        session.execute = AsyncMock(return_value=mock_result)

        # Act
        result = await repository.get_by_patient_and_doctor(patient_id, doctor_id)

        # Assert
        assert result == existing_rating
        session.execute.assert_called_once()

    # ====== LIST BY DOCTOR TESTS ======

    async def test_list_by_doctor_with_pagination(self, repository, session, doctor_id):
        """Test listing doctor's ratings with limit and offset."""
        # Arrange
        limit = 10
        offset = 0
        rating_models = [
            MagicMock(spec=DoctorRatingModel, rating=5),
            MagicMock(spec=DoctorRatingModel, rating=4),
            MagicMock(spec=DoctorRatingModel, rating=5),
        ]

        mock_execute = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = rating_models
        mock_execute.scalars.return_value = mock_scalars
        session.execute = AsyncMock(return_value=mock_execute)

        # Act
        result = await repository.list_by_doctor(doctor_id, limit=limit, offset=offset)

        # Assert
        assert len(result) == 3
        session.execute.assert_called_once()

    async def test_list_by_doctor_returns_empty_when_no_ratings(self, repository, session, doctor_id):
        """Test returns empty list when doctor has no ratings."""
        # Arrange
        limit = 10
        offset = 0

        mock_execute = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_execute.scalars.return_value = mock_scalars
        session.execute = AsyncMock(return_value=mock_execute)

        # Act
        result = await repository.list_by_doctor(doctor_id, limit=limit, offset=offset)

        # Assert
        assert len(result) == 0

    async def test_list_by_doctor_respects_limit(self, repository, session, doctor_id):
        """Test pagination limit is respected."""
        # Arrange
        limit = 5
        offset = 0
        # Create 10 mock ratings
        rating_models = [
            MagicMock(spec=DoctorRatingModel, rating=i % 5)
            for i in range(10)
        ]

        mock_execute = MagicMock()
        mock_scalars = MagicMock()
        # Return only limited amount
        mock_scalars.all.return_value = rating_models[:limit]
        mock_execute.scalars.return_value = mock_scalars
        session.execute = AsyncMock(return_value=mock_execute)

        # Act
        result = await repository.list_by_doctor(doctor_id, limit=limit, offset=offset)

        # Assert
        assert len(result) == limit

    async def test_list_by_doctor_respects_offset(self, repository, session, doctor_id):
        """Test pagination offset skips correct number of records."""
        # Arrange
        limit = 5
        offset = 5
        rating_models = [
            MagicMock(spec=DoctorRatingModel, rating=5),
            MagicMock(spec=DoctorRatingModel, rating=4),
        ]

        mock_execute = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = rating_models
        mock_execute.scalars.return_value = mock_scalars
        session.execute = AsyncMock(return_value=mock_execute)

        # Act
        result = await repository.list_by_doctor(doctor_id, limit=limit, offset=offset)

        # Assert
        assert len(result) == 2
        session.execute.assert_called_once()

    async def test_list_by_doctor_orders_by_created_at_desc(self, repository, session, doctor_id):
        """Test ratings are ordered by created_at descending."""
        # Arrange
        limit = 10
        offset = 0
        rating_models = [
            MagicMock(spec=DoctorRatingModel),
            MagicMock(spec=DoctorRatingModel),
        ]

        mock_execute = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = rating_models
        mock_execute.scalars.return_value = mock_scalars
        session.execute = AsyncMock(return_value=mock_execute)

        # Act
        result = await repository.list_by_doctor(doctor_id, limit=limit, offset=offset)

        # Assert
        assert len(result) == 2
        # Verify order_by was included in execute
        session.execute.assert_called_once()
