from abc import ABC, abstractmethod
from uuid import UUID

from Domain.entities.payment import Payment
from Domain.entities.payment_transaction import PaymentTransaction
from Domain.value_objects.payment_transaction_type import PaymentTransactionType


class IPaymentRepository(ABC):
    """Payment repository interface"""

    @abstractmethod
    async def save(self, payment: Payment) -> None:
        """Save or update payment"""

    @abstractmethod
    async def get_by_id(self, payment_id: UUID) -> Payment | None:
        """Fetch payment by ID"""

    @abstractmethod
    async def get_by_appointment_id(self, appointment_id: UUID) -> Payment | None:
        """Fetch payment by appointment ID"""

    @abstractmethod
    async def get_by_vnpay_txn_ref(self, txn_ref: str) -> Payment | None:
        """Fetch payment by VNPAY transaction reference"""

    @abstractmethod
    async def append_transaction(
        self,
        payment_id: UUID,
        appointment_id: UUID,
        transaction_type: PaymentTransactionType,
        amount: int,
        currency: str = "VND",
        provider_ref: str | None = None,
        response_code: str | None = None,
        metadata: dict | None = None,
    ) -> PaymentTransaction:
        """Append one immutable payment transaction ledger row"""

    @abstractmethod
    async def list_transactions(self, payment_id: UUID) -> list[PaymentTransaction]:
        """List all payment transactions ordered by created_at"""
