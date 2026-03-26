import uuid
from datetime import date

from infrastructure.database.models import DoctorDayOffModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from uuid_extension import UUID7


class DayOffRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, doctor_id: UUID7, off_date: date, reason: str = None):
        model = DoctorDayOffModel(doctor_id=uuid.UUID(str(doctor_id)), off_date=off_date, reason=reason)
        self.session.add(model)
        await self.session.flush()
        return model

    async def delete(self, doctor_id: UUID7, off_date: date):
        await self.session.execute(
            delete(DoctorDayOffModel).where(
                DoctorDayOffModel.doctor_id == uuid.UUID(str(doctor_id)), DoctorDayOffModel.off_date == off_date
            )
        )
        await self.session.flush()
        return True

    async def is_day_off(self, doctor_id: UUID7, off_date: date) -> bool:
        result = await self.session.execute(
            select(DoctorDayOffModel).where(
                DoctorDayOffModel.doctor_id == uuid.UUID(str(doctor_id)), DoctorDayOffModel.off_date == off_date
            )
        )
        return result.scalar_one_or_none() is not None
