import uuid
from typing import List, Optional

from Domain.entities.diagnosis import Diagnosis
from Domain.interfaces.diagnosis_repository import IDiagnosisRepository
from Domain.value_objects.diagnosis_status import DiagnosisStatus
from Domain.value_objects.record_source import RecordSource
from Domain.value_objects.severity import Severity
from infrastructure.database.models import DiagnosisModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class DiagnosisRepository(IDiagnosisRepository):
    def __init__(self, session: AsyncSession):
        self.session = session

    # ------------------------------------------------------------------
    # Mapping helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _to_entity(model: DiagnosisModel) -> Diagnosis:
        return Diagnosis(
            id=model.id,
            patient_id=model.patient_id,
            doctor_id=model.doctor_id,
            appointment_id=model.appointment_id,
            icd10_code=model.icd10_code,
            diagnosis_name=model.diagnosis_name,
            diagnosis_detail=model.diagnosis_detail,
            severity=model.severity,
            status=model.status,
            diagnosed_at=model.diagnosed_at,
            resolved_at=model.resolved_at,
            source=model.source,
            created_at=model.created_at,
        )

    # ------------------------------------------------------------------
    # Interface implementation
    # ------------------------------------------------------------------

    async def save(self, diagnosis: Diagnosis) -> Diagnosis:
        result = await self.session.execute(
            select(DiagnosisModel).where(DiagnosisModel.id == diagnosis.id)
        )
        model = result.scalar_one_or_none()

        if model:
            # Update mutable fields only
            model.status = diagnosis.status
            model.resolved_at = diagnosis.resolved_at
            model.diagnosis_detail = diagnosis.diagnosis_detail
            model.severity = diagnosis.severity
            model.icd10_code = diagnosis.icd10_code
        else:
            model = DiagnosisModel(
                id=diagnosis.id,
                patient_id=diagnosis.patient_id,
                doctor_id=diagnosis.doctor_id,
                appointment_id=diagnosis.appointment_id,
                icd10_code=diagnosis.icd10_code,
                diagnosis_name=diagnosis.diagnosis_name,
                diagnosis_detail=diagnosis.diagnosis_detail,
                severity=diagnosis.severity,
                status=diagnosis.status,
                diagnosed_at=diagnosis.diagnosed_at,
                resolved_at=diagnosis.resolved_at,
                source=diagnosis.source,
            )
            self.session.add(model)

        await self.session.flush()
        await self.session.refresh(model)
        return self._to_entity(model)

    async def get_by_id(self, diagnosis_id: uuid.UUID) -> Optional[Diagnosis]:
        result = await self.session.execute(
            select(DiagnosisModel).where(DiagnosisModel.id == diagnosis_id)
        )
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def list_by_patient(
        self,
        patient_id: uuid.UUID,
        status: Optional[DiagnosisStatus] = None,
    ) -> List[Diagnosis]:
        query = select(DiagnosisModel).where(DiagnosisModel.patient_id == patient_id)
        if status is not None:
            query = query.where(DiagnosisModel.status == status)
        query = query.order_by(DiagnosisModel.diagnosed_at.desc())
        result = await self.session.execute(query)
        return [self._to_entity(m) for m in result.scalars().all()]
