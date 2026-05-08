import uuid
from typing import List

from Domain.entities.vaccination import Vaccination
from Domain.interfaces.vaccination_repository import IVaccinationRepository
from infrastructure.database.models import VaccinationModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class VaccinationRepository(IVaccinationRepository):
    def __init__(self, session: AsyncSession):
        self.session = session

    @staticmethod
    def _to_entity(model: VaccinationModel) -> Vaccination:
        return Vaccination(
            id=model.id,
            patient_id=model.patient_id,
            vaccine_name=model.vaccine_name,
            date_administered=model.date_administered,
            next_due_date=model.next_due_date,
            created_at=model.created_at,
        )

    async def save(self, vaccination: Vaccination) -> Vaccination:
        result = await self.session.execute(
            select(VaccinationModel).where(VaccinationModel.id == vaccination.id)
        )
        model = result.scalar_one_or_none()
        if model:
            model.vaccine_name = vaccination.vaccine_name
            model.date_administered = vaccination.date_administered
            model.next_due_date = vaccination.next_due_date
        else:
            model = VaccinationModel(
                id=vaccination.id,
                patient_id=vaccination.patient_id,
                vaccine_name=vaccination.vaccine_name,
                date_administered=vaccination.date_administered,
                next_due_date=vaccination.next_due_date,
            )
            self.session.add(model)

        await self.session.flush()
        await self.session.refresh(model)
        return self._to_entity(model)

    async def list_by_patient(self, patient_id: uuid.UUID) -> List[Vaccination]:
        result = await self.session.execute(
            select(VaccinationModel)
            .where(VaccinationModel.patient_id == patient_id)
            .order_by(VaccinationModel.date_administered.desc())
        )
        return [self._to_entity(model) for model in result.scalars().all()]