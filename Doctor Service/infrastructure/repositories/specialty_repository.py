from typing import List, Optional

from Domain.entities.specialty import Specialty
from Domain.interfaces.specialty_repository import ISpecialtyRepository
from infrastructure.database.models import SpecialtyModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from uuid_extension import UUID7


class SpecialtyRepository(ISpecialtyRepository):
    def __init__(self, session: AsyncSession):
        self.session = session

    async def save(self, specialty: Specialty) -> Specialty:
        model = SpecialtyModel(id=specialty.id, name=specialty.name, description=specialty.description)
        # Merge to handle updates/inserts
        await self.session.merge(model)
        return specialty

    async def get_by_id(self, specialty_id: UUID7) -> Optional[Specialty]:
        result = await self.session.execute(select(SpecialtyModel).where(SpecialtyModel.id == specialty_id))
        model = result.scalar_one_or_none()
        if not model:
            return None
        return Specialty(id=model.id, name=model.name, description=model.description)

    async def get_by_name(self, name: str) -> Optional[Specialty]:
        result = await self.session.execute(select(SpecialtyModel).where(SpecialtyModel.name == name))
        model = result.scalar_one_or_none()
        if not model:
            return None
        return Specialty(id=model.id, name=model.name, description=model.description)

    async def list_all(self) -> List[Specialty]:
        result = await self.session.execute(select(SpecialtyModel))
        models = result.scalars().all()
        return [Specialty(id=m.id, name=m.name, description=m.description) for m in models]
