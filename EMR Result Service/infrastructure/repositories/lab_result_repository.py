import uuid
from typing import List, Optional

from Domain.entities.lab_result import LabResult
from Domain.interfaces.lab_result_repository import ILabResultRepository
from Domain.value_objects.lab_result_status import LabResultStatus
from infrastructure.database.models import LabResultModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class LabResultRepository(ILabResultRepository):
    def __init__(self, session: AsyncSession):
        self.session = session

    @staticmethod
    def _to_entity(model: LabResultModel) -> LabResult:
        return LabResult(
            id=model.id,
            order_id=model.order_id,
            patient_id=model.patient_id,
            doctor_id=model.doctor_id,
            status=model.status,
            file_url=model.file_url,
            file_type=model.file_type,
            reviewer_doctor_id=model.reviewer_doctor_id,
            required_specialty=model.required_specialty,
            ai_visual_findings=model.ai_visual_findings,
            raw_input_json=model.raw_input_json,
            ai_draft_text=model.ai_draft_text,
            ai_draft_citations=model.ai_draft_citations,
            ai_confidence=model.ai_confidence,
            ai_model_versions=model.ai_model_versions,
            ai_processed_at=model.ai_processed_at,
            doctor_notes=model.doctor_notes,
            verified_by=model.verified_by,
            verified_at=model.verified_at,
            published_text=model.published_text,
            published_findings=model.published_findings,
            published_at=model.published_at,
            created_at=model.created_at,
        )

    async def save(self, result: LabResult) -> LabResult:
        db_result = await self.session.execute(
            select(LabResultModel).where(LabResultModel.id == result.id)
        )
        model = db_result.scalar_one_or_none()

        if model:
            # Update all mutable fields
            model.status = result.status
            model.file_url = result.file_url
            model.file_type = result.file_type
            model.raw_input_json = result.raw_input_json
            model.reviewer_doctor_id = result.reviewer_doctor_id
            model.required_specialty = result.required_specialty
            model.ai_visual_findings = result.ai_visual_findings
            model.ai_draft_text = result.ai_draft_text
            model.ai_draft_citations = result.ai_draft_citations
            model.ai_confidence = result.ai_confidence
            model.ai_model_versions = result.ai_model_versions
            model.ai_processed_at = result.ai_processed_at
            model.doctor_notes = result.doctor_notes
            model.verified_by = result.verified_by
            model.verified_at = result.verified_at
            model.published_text = result.published_text
            model.published_findings = result.published_findings
            model.published_at = result.published_at
        else:
            model = LabResultModel(
                id=result.id,
                order_id=result.order_id,
                patient_id=result.patient_id,
                doctor_id=result.doctor_id,
                status=result.status,
                file_url=result.file_url,
                file_type=result.file_type,
            )
            self.session.add(model)

        await self.session.flush()
        await self.session.refresh(model)
        return self._to_entity(model)

    async def get_by_id(self, result_id: uuid.UUID) -> Optional[LabResult]:
        db_result = await self.session.execute(
            select(LabResultModel).where(LabResultModel.id == result_id)
        )
        model = db_result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def list(
        self,
        patient_id: Optional[uuid.UUID] = None,
        doctor_id: Optional[uuid.UUID] = None,
        status: Optional[LabResultStatus] = None,
        reviewer_doctor_id: Optional[uuid.UUID] = None,
        required_specialty: Optional[str] = None,
        open_claim: Optional[bool] = None,
    ) -> List[LabResult]:
        """List lab results with optional specialty-routing filters.

        open_claim=True  → reviewer_doctor_id IS NULL (unclaimed specialty results)
        reviewer_doctor_id → results assigned to a specific reviewer
        required_specialty → filter by specialty worklist
        """
        query = select(LabResultModel)
        if patient_id is not None:
            query = query.where(LabResultModel.patient_id == patient_id)
        if doctor_id is not None:
            query = query.where(LabResultModel.doctor_id == doctor_id)
        if status is not None:
            query = query.where(LabResultModel.status == status)
        if reviewer_doctor_id is not None:
            query = query.where(LabResultModel.reviewer_doctor_id == reviewer_doctor_id)
        if required_specialty is not None:
            query = query.where(LabResultModel.required_specialty == required_specialty)
        if open_claim is True:
            query = query.where(LabResultModel.reviewer_doctor_id.is_(None))
            query = query.where(LabResultModel.required_specialty.is_not(None))
        query = query.order_by(LabResultModel.created_at.desc())
        db_result = await self.session.execute(query)
        return [self._to_entity(m) for m in db_result.scalars().all()]

    async def list_by_order_ids(self, order_ids: List[uuid.UUID]) -> List[LabResult]:
        if not order_ids:
            return []
        query = select(LabResultModel).where(LabResultModel.order_id.in_(order_ids))
        db_result = await self.session.execute(query)
        return [self._to_entity(m) for m in db_result.scalars().all()]

    async def delete(self, result_id: uuid.UUID) -> None:
        db_result = await self.session.execute(
            select(LabResultModel).where(LabResultModel.id == result_id)
        )
        model = db_result.scalar_one_or_none()
        if model:
            await self.session.delete(model)
            await self.session.flush()
