from abc import ABC, abstractmethod
from datetime import date
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
        appointment_id: UUID | None,
        transaction_type: PaymentTransactionType,
        amount: int,
        currency: str = "VND",
        provider_ref: str | None = None,
        response_code: str | None = None,
        metadata: dict | None = None,
    ) -> PaymentTransaction:
        """Append one immutable payment transaction ledger row"""

    @abstractmethod
    async def list_by_patient_id(self, patient_id: UUID) -> list[Payment]:
        """List all payments for a patient ordered by created_at desc"""

    @abstractmethod
    async def list_history_by_patient_id(
        self,
        patient_id: UUID,
        *,
        from_date: date | None = None,
        to_date: date | None = None,
        status: str | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[Payment], int]:
        """List filtered payment history for one patient and return items with total count"""

    @abstractmethod
    async def list_history(
        self,
        *,
        from_date: date | None = None,
        to_date: date | None = None,
        status: str | None = None,
        patient_id: UUID | None = None,
        doctor_id: UUID | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[Payment], int]:
        """List filtered payment history across all patients and return items with total count"""

    @abstractmethod
    async def update_appointment_status(
        self, appointment_id: UUID, appointment_status: str
    ) -> None:
        """Update cached appointment_status on the payment record for this appointment"""

    @abstractmethod
    async def get_by_reference_id(self, reference_id: UUID) -> Payment | None:
        """Fetch LAB_ORDER payment by reference_id (= lab_order_id)."""

    @abstractmethod
    async def list_by_reference_ids(self, reference_ids: list[UUID]) -> list[Payment]:
        """Fetch LAB_ORDER payments by their reference ids."""

    @abstractmethod
    async def delete_by_reference_id(self, reference_id: UUID) -> None:
        """Delete a payment by its LAB_ORDER reference id."""

    @abstractmethod
    async def list_transactions(self, payment_id: UUID) -> list[PaymentTransaction]:
        """List all payment transactions ordered by created_at"""
