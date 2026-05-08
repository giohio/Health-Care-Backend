"""Use cases for lab order template management.

Templates come in two flavours:
  SYSTEM  — created by admin, visible to all doctors
  PERSONAL — created by a specific doctor, visible only to that doctor

Permission rules:
  - Doctors can create PERSONAL templates.
  - Admins can create SYSTEM templates.
  - Doctors can delete their own PERSONAL templates only.
  - Admins can delete any template.
  - All doctors can list SYSTEM + their own PERSONAL templates.
"""
import uuid
from typing import List, Optional

from Application.dtos import (
    CreateLabOrderFromTemplateRequest,
    CreateLabOrderTemplateRequest,
    LabOrderResponse,
    LabOrderTemplateResponse,
)
from Application.exceptions import LabOrderNotFoundError
from Domain.entities.lab_order import LabOrder
from Domain.entities.lab_order_template import LabOrderTemplate, TemplateCreatorType, TemplateTestItem
from Domain.value_objects.order_priority import OrderPriority
from Domain.value_objects.test_type import TestType
from infrastructure.repositories.lab_order_repository import LabOrderRepository
from infrastructure.repositories.lab_order_template_repository import LabOrderTemplateRepository


class CreateLabOrderTemplateUseCase:
    def __init__(self, template_repo: LabOrderTemplateRepository) -> None:
        self._repo = template_repo

    async def execute(
        self,
        request: CreateLabOrderTemplateRequest,
        creator_id: uuid.UUID,
        creator_role: str,
    ) -> LabOrderTemplateResponse:
        if creator_role == "admin":
            creator_type = TemplateCreatorType.SYSTEM
            effective_creator_id = None
        else:
            creator_type = TemplateCreatorType.PERSONAL
            effective_creator_id = creator_id

        test_items = [
            TemplateTestItem(
                test_name=item.test_name,
                test_type=item.test_type,
                instructions=item.instructions,
                priority=item.priority,
            )
            for item in request.test_items
        ]

        template = LabOrderTemplate(
            id=uuid.uuid4(),
            name=request.name,
            description=request.description,
            department=request.department,
            test_items=test_items,
            creator_type=creator_type,
            creator_id=effective_creator_id,
        )

        saved = await self._repo.save(template)
        return LabOrderTemplateResponse.model_validate(saved)


class ListLabOrderTemplatesUseCase:
    def __init__(self, template_repo: LabOrderTemplateRepository) -> None:
        self._repo = template_repo

    async def execute(
        self,
        caller_id: uuid.UUID,
        caller_role: str,
        department: Optional[str] = None,
    ) -> List[LabOrderTemplateResponse]:
        if caller_role == "admin":
            # Admins see all system templates
            templates = await self._repo.list_system(department=department)
        else:
            templates = await self._repo.list_for_doctor(
                doctor_id=caller_id, department=department
            )
        return [LabOrderTemplateResponse.model_validate(t) for t in templates]


class DeleteLabOrderTemplateUseCase:
    def __init__(self, template_repo: LabOrderTemplateRepository) -> None:
        self._repo = template_repo

    async def execute(
        self,
        template_id: uuid.UUID,
        caller_id: uuid.UUID,
        caller_role: str,
    ) -> None:
        template = await self._repo.get_by_id(template_id)
        if template is None:
            raise ValueError("Template not found.")

        if caller_role != "admin":
            # Doctors can only delete their own PERSONAL templates
            if template.creator_type == TemplateCreatorType.SYSTEM:
                raise PermissionError("Cannot delete a SYSTEM template.")
            if template.creator_id != caller_id:
                raise PermissionError("Cannot delete another doctor's template.")

        await self._repo.delete(template_id)


class CreateOrdersFromTemplateUseCase:
    """Batch-create LabOrders from a template in a single request."""

    def __init__(
        self,
        template_repo: LabOrderTemplateRepository,
        order_repo: LabOrderRepository,
    ) -> None:
        self._template_repo = template_repo
        self._order_repo = order_repo

    async def execute(
        self, request: CreateLabOrderFromTemplateRequest
    ) -> List[LabOrderResponse]:
        template = await self._template_repo.get_by_id(request.template_id)
        if template is None:
            raise ValueError("Template not found.")

        created: List[LabOrderResponse] = []
        for item in template.test_items:
            try:
                test_type = TestType(item.test_type) if item.test_type else None
            except ValueError:
                test_type = None

            try:
                priority = OrderPriority(item.priority)
            except ValueError:
                priority = OrderPriority.ROUTINE

            order = LabOrder(
                id=uuid.uuid4(),
                patient_id=request.patient_id,
                doctor_id=request.doctor_id,
                appointment_id=request.appointment_id,
                test_name=item.test_name,
                test_type=test_type,
                department=template.department,
                instructions=item.instructions,
                priority=priority,
            )
            saved = await self._order_repo.save(order)
            created.append(LabOrderResponse.model_validate(saved))

        return created
