from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from typing import List, Optional
from Domain.entities.doctor import Doctor
from Domain.interfaces.doctor_repository import IDoctorRepository
from infrastructure.database.models import DoctorModel, DoctorScheduleModel
from Domain.value_objects.day_of_week import DayOfWeek
from datetime import time
from uuid_extension import UUID7

class DoctorRepository(IDoctorRepository):
    def __init__(self, session: AsyncSession):
        self.session = session

    async def save(self, doctor: Doctor) -> Doctor:
        model = DoctorModel(
            user_id=doctor.user_id,
            specialty_id=doctor.specialty_id,
            full_name=doctor.full_name,
            title=doctor.title,
            experience_years=doctor.experience_years
        )
        await self.session.merge(model)
        return doctor

    async def get_by_id(self, user_id: UUID7) -> Optional[Doctor]:
        result = await self.session.execute(
            select(DoctorModel).where(DoctorModel.user_id == user_id)
        )
        model = result.scalar_one_or_none()
        if not model:
            return None
        return Doctor(
            user_id=model.user_id,
            specialty_id=model.specialty_id,
            full_name=model.full_name,
            title=model.title,
            experience_years=model.experience_years
        )

    async def list_by_specialty(self, specialty_id: UUID7) -> List[Doctor]:
        result = await self.session.execute(
            select(DoctorModel).where(DoctorModel.specialty_id == specialty_id)
        )
        models = result.scalars().all()
        return [
            Doctor(
                user_id=m.user_id,
                specialty_id=m.specialty_id,
                full_name=m.full_name,
                title=m.title,
                experience_years=m.experience_years
            ) for m in models
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
                    DoctorScheduleModel.end_time > time_slot
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
                experience_years=m.experience_years
            ) for m in models
        ]
