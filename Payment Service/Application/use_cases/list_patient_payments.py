from uuid import UUID

from Domain.interfaces.payment_repository import IPaymentRepository


class ListPatientPaymentsUseCase:
    """List all payments belonging to a patient."""

    def __init__(self, payment_repo: IPaymentRepository):
        self.payment_repo = payment_repo

    async def execute(self, patient_id: UUID) -> list[dict]:
        payments = await self.payment_repo.list_by_patient_id(patient_id)
        return [
            {
                "id": str(p.id),
                "appointment_id": str(p.appointment_id),
                "status": p.status.value,
                "amount": p.amount,
                "currency": p.currency,
                "payment_url": p.payment_url,
                "vnpay_txn_ref": p.vnpay_txn_ref,
                "paid_at": p.paid_at.isoformat() if p.paid_at else None,
                "created_at": p.created_at.isoformat() if p.created_at else None,
            }
            for p in payments
        ]
