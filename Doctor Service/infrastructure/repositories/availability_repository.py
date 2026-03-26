import uuid
from datetime import time

from infrastructure.database.models import DoctorAvailabilityModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from uuid_extension import UUID7


class AvailabilityRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def upsert(
        self, doctor_id: UUID7, day_of_week: int, start_time: time, end_time: time, break_start, break_end, max_patients
    ):
        result = await self.session.execute(
            select(DoctorAvailabilityModel).where(
                DoctorAvailabilityModel.doctor_id == uuid.UUID(str(doctor_id)),
                DoctorAvailabilityModel.day_of_week == day_of_week,
            )
        )
        existing = result.scalar_one_or_none()

        if existing:
            existing.start_time = start_time
            existing.end_time = end_time
            existing.break_start = break_start
            existing.break_end = break_end
            existing.max_patients = max_patients
            await self.session.flush()
            return existing
        else:
            model = DoctorAvailabilityModel(
                doctor_id=uuid.UUID(str(doctor_id)),
                day_of_week=day_of_week,
                start_time=start_time,
                end_time=end_time,
                break_start=break_start,
                break_end=break_end,
                max_patients=max_patients,
            )
            self.session.add(model)
            await self.session.flush()
            return model

    async def get_by_doctor_and_day(self, doctor_id: UUID7, day_of_week: int):
        result = await self.session.execute(
            select(DoctorAvailabilityModel).where(
                DoctorAvailabilityModel.doctor_id == uuid.UUID(str(doctor_id)),
                DoctorAvailabilityModel.day_of_week == day_of_week,
                DoctorAvailabilityModel.is_active.is_(True),
            )
        )
        return result.scalars().all()

    async def list_by_doctor(self, doctor_id: UUID7):
        result = await self.session.execute(
            select(DoctorAvailabilityModel)
            .where(DoctorAvailabilityModel.doctor_id == uuid.UUID(str(doctor_id)))
            .order_by(DoctorAvailabilityModel.day_of_week)
        )
        return result.scalars().all()

    async def get_by_doctor(self, doctor_id: UUID7):
        return await self.list_by_doctor(doctor_id)
