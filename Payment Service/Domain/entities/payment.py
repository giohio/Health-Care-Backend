from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from Domain.value_objects.payment_status import PaymentStatus


@dataclass
class Payment:
    """Payment entity - domain model"""

    id: UUID
    appointment_id: UUID
    patient_id: UUID
    doctor_id: UUID
    amount: int  # in VND
    currency: str = "VND"
    status: PaymentStatus = PaymentStatus.PENDING
    vnpay_txn_ref: str | None = None
    vnpay_provider_ref: str | None = None
    payment_url: str | None = None
    paid_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def mark_as_paid(self, provider_ref: str, paid_at: datetime) -> None:
        """Mark payment as successfully paid"""
        self.status = PaymentStatus.PAID
        self.vnpay_provider_ref = provider_ref
        self.paid_at = paid_at

    def mark_as_failed(self) -> None:
        """Mark payment as failed"""
        self.status = PaymentStatus.FAILED

    def mark_as_expired(self) -> None:
        """Mark payment as expired"""
        self.status = PaymentStatus.EXPIRED

    def mark_as_refunded(self) -> None:
        """Mark payment as refunded"""
        self.status = PaymentStatus.REFUNDED

    def is_expired(self, now: datetime) -> bool:
        """Check if payment has expired (15 minutes from creation)"""
        if not self.created_at:
            return False
        from datetime import timedelta

        return (now - self.created_at) > timedelta(minutes=15)
