from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from typing import List, Optional
from Domain.entities.doctor_schedule import DoctorSchedule
from Domain.interfaces.schedule_repository import IScheduleRepository
from infrastructure.database.models import DoctorScheduleModel
from Domain.value_objects.day_of_week import DayOfWeek
from uuid_extension import UUID7

class ScheduleRepository(IScheduleRepository):
    def __init__(self, session: AsyncSession):
        self.session = session

    async def save(self, schedule: DoctorSchedule) -> DoctorSchedule:
        model = DoctorScheduleModel(
            id=schedule.id,
            doctor_id=schedule.doctor_id,
            day_of_week=schedule.day_of_week,
            start_time=schedule.start_time,
            end_time=schedule.end_time,
            slot_duration_minutes=schedule.slot_duration_minutes
        )
        await self.session.merge(model)
        return schedule

    async def delete(self, schedule_id: UUID7) -> None:
        await self.session.execute(
            delete(DoctorScheduleModel).where(DoctorScheduleModel.id == schedule_id)
        )

    async def get_by_doctor_and_day(self, doctor_id: UUID7, day: DayOfWeek) -> List[DoctorSchedule]:
        result = await self.session.execute(
            select(DoctorScheduleModel)
            .where(DoctorScheduleModel.doctor_id == doctor_id)
            .where(DoctorScheduleModel.day_of_week == day)
        )
        models = result.scalars().all()
        return [
            DoctorSchedule(
                id=m.id,
                doctor_id=m.doctor_id,
                day_of_week=m.day_of_week,
                start_time=m.start_time,
                end_time=m.end_time,
                slot_duration_minutes=m.slot_duration_minutes
            ) for m in models
        ]

    async def list_by_doctor(self, doctor_id: UUID7) -> List[DoctorSchedule]:
        result = await self.session.execute(
            select(DoctorScheduleModel).where(DoctorScheduleModel.doctor_id == doctor_id)
        )
        models = result.scalars().all()
        return [
            DoctorSchedule(
                id=m.id,
                doctor_id=m.doctor_id,
                day_of_week=m.day_of_week,
                start_time=m.start_time,
                end_time=m.end_time,
                slot_duration_minutes=m.slot_duration_minutes
            ) for m in models
        ]
