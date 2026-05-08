from datetime import date
from uuid import UUID

from Application.use_cases.payment_history_models import PaymentHistoryPage, serialize_payment
from Domain.interfaces.payment_repository import IPaymentRepository
from Domain.value_objects.payment_status import PaymentStatus


class ListPatientPaymentHistoryUseCase:
    def __init__(self, payment_repo: IPaymentRepository):
        self.payment_repo = payment_repo

    async def execute(
        self,
        patient_id: UUID,
        *,
        from_date: date | None = None,
        to_date: date | None = None,
        status: PaymentStatus | None = None,
        page: int = 1,
        limit: int = 20,
    ) -> PaymentHistoryPage:
        if from_date and to_date and from_date > to_date:
            raise ValueError("from_date must be less than or equal to to_date")

        offset = (page - 1) * limit
        payments, total = await self.payment_repo.list_history_by_patient_id(
            patient_id,
            from_date=from_date,
            to_date=to_date,
            status=status,
            offset=offset,
            limit=limit,
        )
        total_pages = (total + limit - 1) // limit if total else 0
        return PaymentHistoryPage(
            items=[serialize_payment(payment) for payment in payments],
            total=total,
            page=page,
            limit=limit,
            total_pages=total_pages,
        )