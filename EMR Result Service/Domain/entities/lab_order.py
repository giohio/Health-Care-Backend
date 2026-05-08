from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from uuid import UUID

from Domain.value_objects.order_priority import OrderPriority
from Domain.value_objects.test_type import TestType


@dataclass
class LabOrder:
    id: UUID
    patient_id: UUID
    doctor_id: UUID
    test_name: str
    appointment_id: Optional[UUID] = None
    test_type: Optional[TestType] = None
    department: Optional[str] = None
    instructions: Optional[str] = None
    priority: OrderPriority = OrderPriority.ROUTINE
    fee: int = 0
    payment_status: str = "UNPAID"  # UNPAID | PAID | REFUND_PENDING
    ordered_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
