from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from Domain.value_objects.payment_transaction_type import PaymentTransactionType


@dataclass
class PaymentTransaction:
    id: UUID
    payment_id: UUID
    appointment_id: UUID
    transaction_type: PaymentTransactionType
    amount: int
    currency: str = "VND"
    provider_ref: str | None = None
    response_code: str | None = None
    metadata: dict | None = None
    created_at: datetime | None = None
