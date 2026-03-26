"""Unit tests for Doctor repository methods - simplified integration tests."""
import pytest
import pytest_asyncio
from datetime import time
from uuid import uuid4
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from infrastructure.repositories.availability_repository import AvailabilityRepository
from infrastructure.database.models import Base

pytest.importorskip("aiosqlite")


@pytest_asyncio.fixture(scope="function")
async def async_session():
    """Create in-memory SQLite database for testing."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session_maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session_maker() as session:
        yield session

    await engine.dispose()


@pytest.mark.asyncio
class TestAvailabilityRepositoryIntegration:
    """Integration tests for AvailabilityRepository with real SQLite."""

    async def test_upsert_creates_new_availability(self, async_session):
        """Test upsert creates new availability when not exists."""
        # Arrange
        repo = AvailabilityRepository(async_session)
        doctor_id = uuid4()
        day_of_week = 1
        start_time = time(8, 0)
        end_time = time(17, 0)
        break_start = time(12, 0)
        break_end = time(13, 0)
        max_patients = 10

        # Act
        result = await repo.upsert(
            doctor_id=doctor_id,
            day_of_week=day_of_week,
            start_time=start_time,
            end_time=end_time,
            break_start=break_start,
            break_end=break_end,
            max_patients=max_patients,
        )
        await async_session.commit()

        # Assert
        assert result is not None
        assert result.doctor_id == doctor_id
        assert result.day_of_week == day_of_week
        assert result.start_time == start_time

    async def test_upsert_updates_existing_availability(self, async_session):
        """Test upsert updates existing availability record."""
        # Arrange
        repo = AvailabilityRepository(async_session)
        doctor_id = uuid4()
        day_of_week = 1

        # Create initial
        await repo.upsert(
            doctor_id=doctor_id,
            day_of_week=day_of_week,
            start_time=time(8, 0),
            end_time=time(17, 0),
            break_start=time(12, 0),
            break_end=time(13, 0),
            max_patients=10,
        )
        await async_session.commit()

        # Update
        result = await repo.upsert(
            doctor_id=doctor_id,
            day_of_week=day_of_week,
            start_time=time(9, 0),
            end_time=time(18, 0),
            break_start=time(13, 0),
            break_end=time(14, 0),
            max_patients=15,
        )
        await async_session.commit()

        # Assert
        assert result.start_time == time(9, 0)
        assert result.max_patients == 15

    async def test_list_by_doctor_returns_availabilities(self, async_session):
        """Test listing all availabilities for doctor."""
        # Arrange
        repo = AvailabilityRepository(async_session)
        doctor_id = uuid4()

        # Create multiple availabilities
        for day in range(1, 6):
            await repo.upsert(
                doctor_id=doctor_id,
                day_of_week=day,
                start_time=time(8, 0),
                end_time=time(17, 0),
                break_start=time(12, 0),
                break_end=time(13, 0),
                max_patients=10,
            )
        await async_session.commit()

        # Act
        results = await repo.list_by_doctor(doctor_id)

        # Assert
        assert len(results) == 5
        assert all(model.doctor_id == doctor_id for model in results)

    async def test_get_by_doctor_and_day_returns_active_availability(self, async_session):
        """Test retrieving availability for specific day."""
        # Arrange
        repo = AvailabilityRepository(async_session)
        doctor_id = uuid4()
        day_of_week = 3

        await repo.upsert(
            doctor_id=doctor_id,
            day_of_week=day_of_week,
            start_time=time(8, 0),
            end_time=time(17, 0),
            break_start=time(12, 0),
            break_end=time(13, 0),
            max_patients=10,
        )
        await async_session.commit()

        # Act
        results = await repo.get_by_doctor_and_day(doctor_id, day_of_week)

        # Assert
        assert len(results) == 1
        assert results[0].day_of_week == day_of_week
