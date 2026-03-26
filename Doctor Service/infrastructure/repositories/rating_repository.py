import uuid

from Domain.interfaces.rating_repository import IRatingRepository
from infrastructure.database.models import DoctorRatingModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from uuid_extension import UUID7


class RatingRepository(IRatingRepository):
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, doctor_id: UUID7, patient_id: UUID7, rating: int, comment: str | None):
        model = DoctorRatingModel(
            doctor_id=uuid.UUID(str(doctor_id)), patient_id=uuid.UUID(str(patient_id)), rating=rating, comment=comment
        )
        self.session.add(model)
        await self.session.flush()
        return model

    async def get_by_patient_and_doctor(self, patient_id: UUID7, doctor_id: UUID7):
        result = await self.session.execute(
            select(DoctorRatingModel).where(
                DoctorRatingModel.patient_id == uuid.UUID(str(patient_id)),
                DoctorRatingModel.doctor_id == uuid.UUID(str(doctor_id)),
            )
        )
        return result.scalar_one_or_none()

    async def list_by_doctor(self, doctor_id: UUID7, limit: int, offset: int):
        result = await self.session.execute(
            select(DoctorRatingModel)
            .where(DoctorRatingModel.doctor_id == uuid.UUID(str(doctor_id)))
            .order_by(DoctorRatingModel.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return result.scalars().all()

    async def get_average_rating(self, doctor_id: UUID7) -> float:
        result = await self.session.execute(
            select(func.avg(DoctorRatingModel.rating)).where(DoctorRatingModel.doctor_id == uuid.UUID(str(doctor_id)))
        )
        avg = result.scalar()
        return float(avg) if avg else 0.0
