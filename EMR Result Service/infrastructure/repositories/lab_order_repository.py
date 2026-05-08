import uuid
from typing import List, Optional

from Domain.entities.lab_order import LabOrder
from Domain.interfaces.lab_order_repository import ILabOrderRepository
from infrastructure.database.models import LabOrderModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class LabOrderRepository(ILabOrderRepository):
    def __init__(self, session: AsyncSession):
        self.session = session

    @staticmethod
    def _to_entity(model: LabOrderModel) -> LabOrder:
        return LabOrder(
            id=model.id,
            patient_id=model.patient_id,
            doctor_id=model.doctor_id,
            appointment_id=model.appointment_id,
            test_name=model.test_name,
            test_type=model.test_type,
            department=model.department,
            instructions=model.instructions,
            priority=model.priority,
            fee=model.fee,
            payment_status=model.payment_status,
            ordered_at=model.ordered_at,
            created_at=model.created_at,
        )

    async def save(self, order: LabOrder) -> LabOrder:
        stmt = select(LabOrderModel).where(LabOrderModel.id == order.id)
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        
        if model:
            # Update existing
            model.payment_status = order.payment_status
        else:
            # Create new
            model = LabOrderModel(
                id=order.id,
                patient_id=order.patient_id,
                doctor_id=order.doctor_id,
                appointment_id=order.appointment_id,
                test_name=order.test_name,
                test_type=order.test_type,
                department=order.department,
                instructions=order.instructions,
                priority=order.priority,
                fee=order.fee,
                payment_status=order.payment_status,
            )
            self.session.add(model)
        await self.session.flush()
        await self.session.refresh(model)
        return self._to_entity(model)

    async def get_by_id(self, order_id: uuid.UUID) -> Optional[LabOrder]:
        result = await self.session.execute(
            select(LabOrderModel).where(LabOrderModel.id == order_id)
        )
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def list(
        self,
        patient_id: Optional[uuid.UUID] = None,
        doctor_id: Optional[uuid.UUID] = None,
    ) -> List[LabOrder]:
        query = select(LabOrderModel)
        if patient_id is not None:
            query = query.where(LabOrderModel.patient_id == patient_id)
        if doctor_id is not None:
            query = query.where(LabOrderModel.doctor_id == doctor_id)
        query = query.order_by(LabOrderModel.created_at.desc())
        result = await self.session.execute(query)
        return [self._to_entity(m) for m in result.scalars().all()]

    async def list_by_appointment_id(self, appointment_id: uuid.UUID) -> List[LabOrder]:
        query = (
            select(LabOrderModel)
            .where(LabOrderModel.appointment_id == appointment_id)
            .order_by(LabOrderModel.created_at.asc())
        )
        result = await self.session.execute(query)
        return [self._to_entity(m) for m in result.scalars().all()]

    async def delete(self, order_id: uuid.UUID) -> None:
        result = await self.session.execute(
            select(LabOrderModel).where(LabOrderModel.id == order_id)
        )
        model = result.scalar_one_or_none()
        if model is None:
            raise ValueError(f"Lab order {order_id} not found.")
        await self.session.delete(model)
        await self.session.flush()
