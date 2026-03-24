from uuid import UUID

from Domain.interfaces.payment_repository import IPaymentRepository


class GetPaymentUseCase:
    """Get payment record by appointment ID"""

    def __init__(self, payment_repo: IPaymentRepository):
        self.payment_repo = payment_repo

    async def execute(self, appointment_id: UUID) -> dict:
        """
        Fetch payment record

        Returns: {id, appointment_id, status, payment_url, vnpay_txn_ref, amount}
        """
        payment = await self.payment_repo.get_by_appointment_id(appointment_id)
        if not payment:
            raise ValueError(f"Payment not found for appointment {appointment_id}")
        transactions = await self.payment_repo.list_transactions(payment.id)

        return {
            "id": str(payment.id),
            "appointment_id": str(payment.appointment_id),
            "patient_id": str(payment.patient_id),
            "status": payment.status.value,
            "payment_url": payment.payment_url,
            "vnpay_txn_ref": payment.vnpay_txn_ref,
            "amount": payment.amount,
            "currency": payment.currency,
            "transactions": [
                {
                    "id": str(txn.id),
                    "transaction_type": txn.transaction_type.value,
                    "amount": txn.amount,
                    "currency": txn.currency,
                    "provider_ref": txn.provider_ref,
                    "response_code": txn.response_code,
                    "metadata": txn.metadata,
                    "created_at": txn.created_at.isoformat() if txn.created_at else None,
                }
                for txn in transactions
            ],
        }
