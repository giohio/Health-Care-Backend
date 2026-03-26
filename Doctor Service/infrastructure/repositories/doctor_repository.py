from datetime import time
from typing import List, Optional

from Domain.entities.doctor import Doctor
from Domain.interfaces.doctor_repository import IDoctorRepository
from Domain.value_objects.day_of_week import DayOfWeek
from infrastructure.database.models import DoctorModel, DoctorScheduleModel
from sqlalchemy import and_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from uuid_extension import UUID7


class DoctorRepository(IDoctorRepository):
    def __init__(self, session: AsyncSession):
        self.session = session

    async def save(self, doctor: Doctor) -> Doctor:
        stmt = pg_insert(DoctorModel).values(
            user_id=doctor.user_id,
            specialty_id=doctor.specialty_id,
            full_name=doctor.full_name,
            title=doctor.title,
            experience_years=doctor.experience_years,
            auto_confirm=doctor.auto_confirm,
            confirmation_timeout_minutes=doctor.confirmation_timeout_minutes,
        )

        stmt = stmt.on_conflict_do_update(
            index_elements=[DoctorModel.user_id],
            set_={
                "specialty_id": stmt.excluded.specialty_id,
                "full_name": stmt.excluded.full_name,
                "title": stmt.excluded.title,
                "experience_years": stmt.excluded.experience_years,
                "auto_confirm": stmt.excluded.auto_confirm,
                "confirmation_timeout_minutes": stmt.excluded.confirmation_timeout_minutes,
            },
        )

        await self.session.execute(stmt)
        return doctor

    async def get_by_id(self, user_id: UUID7) -> Optional[Doctor]:
        result = await self.session.execute(select(DoctorModel).where(DoctorModel.user_id == user_id))
        model = result.scalar_one_or_none()
        if not model:
            return None
        return Doctor(
            user_id=model.user_id,
            specialty_id=model.specialty_id,
            full_name=model.full_name,
            title=model.title,
            experience_years=model.experience_years,
            auto_confirm=model.auto_confirm,
            confirmation_timeout_minutes=model.confirmation_timeout_minutes,
        )

    async def list_by_specialty(self, specialty_id: UUID7) -> List[Doctor]:
        result = await self.session.execute(select(DoctorModel).where(DoctorModel.specialty_id == specialty_id))
        models = result.scalars().all()
        return [
            Doctor(
                user_id=m.user_id,
                specialty_id=m.specialty_id,
                full_name=m.full_name,
                title=m.title,
                experience_years=m.experience_years,
                auto_confirm=m.auto_confirm,
                confirmation_timeout_minutes=m.confirmation_timeout_minutes,
            )
            for m in models
        ]

    async def search_available(self, specialty_id: UUID7, day_of_week: int, time_slot: time) -> List[Doctor]:
        # Convert int to DayOfWeek enum
        day_enum = DayOfWeek(day_of_week)

        query = (
            select(DoctorModel)
            .join(DoctorScheduleModel)
            .where(
                and_(
                    DoctorModel.specialty_id == specialty_id,
                    DoctorScheduleModel.day_of_week == day_enum,
                    DoctorScheduleModel.start_time <= time_slot,
                    DoctorScheduleModel.end_time > time_slot,
                )
            )
        )

        result = await self.session.execute(query)
        models = result.scalars().all()
        return [
            Doctor(
                user_id=m.user_id,
                specialty_id=m.specialty_id,
                full_name=m.full_name,
                title=m.title,
                experience_years=m.experience_years,
                auto_confirm=m.auto_confirm,
                confirmation_timeout_minutes=m.confirmation_timeout_minutes,
            )
            for m in models
        ]

    async def update_average_rating(self, doctor_id: UUID7, average_rating: float):
        import uuid

        from sqlalchemy import update

        await self.session.execute(
            update(DoctorModel)
            .where(DoctorModel.user_id == uuid.UUID(str(doctor_id)))
            .values(average_rating=average_rating, rating_count=DoctorModel.rating_count + 1)
        )
        await self.session.flush()
