import uuid
from typing import List, Optional

from Domain.entities.medication import Medication
from Domain.interfaces.medication_repository import IMedicationRepository
from Domain.value_objects.medication_status import MedicationStatus
from infrastructure.database.models import MedicationModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class MedicationRepository(IMedicationRepository):
    def __init__(self, session: AsyncSession):
        self.session = session

    # ------------------------------------------------------------------
    # Mapping helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _to_entity(model: MedicationModel) -> Medication:
        return Medication(
            id=model.id,
            patient_id=model.patient_id,
            doctor_id=model.doctor_id,
            appointment_id=model.appointment_id,
            drug_name=model.drug_name,
            dosage=model.dosage,
            frequency=model.frequency,
            route=model.route,
            start_date=model.start_date,
            end_date=model.end_date,
            status=model.status,
            notes=model.notes,
            created_at=model.created_at,
        )

    # ------------------------------------------------------------------
    # Interface implementation
    # ------------------------------------------------------------------

    async def save(self, medication: Medication) -> Medication:
        result = await self.session.execute(
            select(MedicationModel).where(MedicationModel.id == medication.id)
        )
        model = result.scalar_one_or_none()

        if model:
            # Update mutable fields only
            model.status = medication.status
            model.end_date = medication.end_date
            model.dosage = medication.dosage
            model.frequency = medication.frequency
            model.route = medication.route
            model.notes = medication.notes
        else:
            model = MedicationModel(
                id=medication.id,
                patient_id=medication.patient_id,
                doctor_id=medication.doctor_id,
                appointment_id=medication.appointment_id,
                drug_name=medication.drug_name,
                dosage=medication.dosage,
                frequency=medication.frequency,
                route=medication.route,
                start_date=medication.start_date,
                end_date=medication.end_date,
                status=medication.status,
                notes=medication.notes,
            )
            self.session.add(model)

        await self.session.flush()
        await self.session.refresh(model)
        return self._to_entity(model)

    async def get_by_id(self, medication_id: uuid.UUID) -> Optional[Medication]:
        result = await self.session.execute(
            select(MedicationModel).where(MedicationModel.id == medication_id)
        )
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def list_by_patient(
        self,
        patient_id: uuid.UUID,
        status: Optional[MedicationStatus] = None,
    ) -> List[Medication]:
        query = select(MedicationModel).where(MedicationModel.patient_id == patient_id)
        if status is not None:
            query = query.where(MedicationModel.status == status)
        query = query.order_by(MedicationModel.start_date.desc())
        result = await self.session.execute(query)
        return [self._to_entity(m) for m in result.scalars().all()]
