import uuid
from typing import List, Optional

from Domain.entities.lab_order_template import LabOrderTemplate, TemplateCreatorType, TemplateTestItem
from infrastructure.database.models import LabOrderTemplateModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class LabOrderTemplateRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @staticmethod
    def _to_entity(model: LabOrderTemplateModel) -> LabOrderTemplate:
        test_items = [
            TemplateTestItem(
                test_name=item.get("test_name", ""),
                test_type=item.get("test_type"),
                instructions=item.get("instructions"),
                priority=item.get("priority", "routine"),
            )
            for item in (model.test_items or [])
        ]
        return LabOrderTemplate(
            id=model.id,
            name=model.name,
            description=model.description,
            department=model.department,
            test_items=test_items,
            creator_type=TemplateCreatorType(model.creator_type),
            creator_id=model.creator_id,
            is_active=model.is_active,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    async def save(self, template: LabOrderTemplate) -> LabOrderTemplate:
        model = LabOrderTemplateModel(
            id=template.id,
            name=template.name,
            description=template.description,
            department=template.department,
            test_items=[
                {
                    "test_name": item.test_name,
                    "test_type": item.test_type,
                    "instructions": item.instructions,
                    "priority": item.priority,
                }
                for item in template.test_items
            ],
            creator_type=template.creator_type.value,
            creator_id=template.creator_id,
            is_active=template.is_active,
        )
        self.session.add(model)
        await self.session.flush()
        await self.session.refresh(model)
        return self._to_entity(model)

    async def get_by_id(self, template_id: uuid.UUID) -> Optional[LabOrderTemplate]:
        result = await self.session.execute(
            select(LabOrderTemplateModel).where(LabOrderTemplateModel.id == template_id)
        )
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def delete(self, template_id: uuid.UUID) -> None:
        result = await self.session.execute(
            select(LabOrderTemplateModel).where(LabOrderTemplateModel.id == template_id)
        )
        model = result.scalar_one_or_none()
        if model:
            await self.session.delete(model)
            await self.session.flush()

    async def list_for_doctor(
        self,
        doctor_id: uuid.UUID,
        department: Optional[str] = None,
    ) -> List[LabOrderTemplate]:
        """Return SYSTEM templates merged with the doctor's PERSONAL templates."""
        query = select(LabOrderTemplateModel).where(
            LabOrderTemplateModel.is_active.is_(True),
            (LabOrderTemplateModel.creator_type == "SYSTEM")
            | (LabOrderTemplateModel.creator_id == doctor_id),
        )
        if department:
            query = query.where(LabOrderTemplateModel.department == department)
        query = query.order_by(
            LabOrderTemplateModel.creator_type,   # PERSONAL < SYSTEM alphabetically → PERSONAL first
            LabOrderTemplateModel.name,
        )
        result = await self.session.execute(query)
        return [self._to_entity(m) for m in result.scalars().all()]

    async def list_system(self, department: Optional[str] = None) -> List[LabOrderTemplate]:
        """Return only SYSTEM templates (admin management)."""
        query = select(LabOrderTemplateModel).where(
            LabOrderTemplateModel.creator_type == "SYSTEM",
            LabOrderTemplateModel.is_active.is_(True),
        )
        if department:
            query = query.where(LabOrderTemplateModel.department == department)
        result = await self.session.execute(query)
        return [self._to_entity(m) for m in result.scalars().all()]
