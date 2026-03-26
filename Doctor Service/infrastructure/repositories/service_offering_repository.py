import uuid

from infrastructure.database.models import DoctorServiceOfferingModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from uuid_extension import UUID7


class ServiceOfferingRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self, doctor_id: UUID7, service_name: str, duration_minutes: int, fee: float, description: str = None
    ):
        model = DoctorServiceOfferingModel(
            doctor_id=uuid.UUID(str(doctor_id)),
            service_name=service_name,
            duration_minutes=duration_minutes,
            fee=fee,
            description=description,
        )
        self.session.add(model)
        await self.session.flush()
        return model

    async def update(self, service_id: UUID7, **kwargs):
        await self.session.execute(
            update(DoctorServiceOfferingModel)
            .where(DoctorServiceOfferingModel.id == uuid.UUID(str(service_id)))
            .values(**kwargs)
        )
        await self.session.flush()

    async def list_by_doctor(self, doctor_id: UUID7):
        result = await self.session.execute(
            select(DoctorServiceOfferingModel).where(DoctorServiceOfferingModel.doctor_id == uuid.UUID(str(doctor_id)))
        )
        return result.scalars().all()

    async def deactivate(self, service_id: UUID7):
        await self.session.execute(
            update(DoctorServiceOfferingModel)
            .where(DoctorServiceOfferingModel.id == uuid.UUID(str(service_id)))
            .values(is_active=False)
        )
        await self.session.flush()
