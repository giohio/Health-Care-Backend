from uuid import UUID

from Domain.entities.payment import Payment
from Domain.entities.payment_transaction import PaymentTransaction
from Domain.interfaces.payment_repository import IPaymentRepository
from Domain.value_objects.payment_status import PaymentStatus
from Domain.value_objects.payment_transaction_type import PaymentTransactionType
from infrastructure.database.models import PaymentModel, PaymentTransactionModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class PaymentRepository(IPaymentRepository):
    def __init__(self, session: AsyncSession):
        self.session = session

    async def save(self, payment: Payment) -> None:
        """Save or update payment"""
        model = await self._find_model(payment.id)
        if model:
            # Update existing
            model.status = payment.status
            model.vnpay_provider_ref = payment.vnpay_provider_ref
            model.payment_url = payment.payment_url
            model.paid_at = payment.paid_at
        else:
            # Create new
            model = PaymentModel(
                id=payment.id,
                appointment_id=payment.appointment_id,
                patient_id=payment.patient_id,
                doctor_id=payment.doctor_id,
                amount=payment.amount,
                currency=payment.currency,
                status=payment.status,
                vnpay_txn_ref=payment.vnpay_txn_ref,
                vnpay_provider_ref=payment.vnpay_provider_ref,
                payment_url=payment.payment_url,
                paid_at=payment.paid_at,
            )
            self.session.add(model)
        await self.session.flush()

    async def get_by_id(self, payment_id: UUID) -> Payment | None:
        """Fetch payment by ID"""
        model = await self._find_model(payment_id)
        return self._to_entity(model) if model else None

    async def get_by_appointment_id(self, appointment_id: UUID) -> Payment | None:
        """Fetch payment by appointment ID"""
        stmt = select(PaymentModel).where(PaymentModel.appointment_id == appointment_id)
        result = await self.session.execute(stmt)
        model = result.scalars().first()
        return self._to_entity(model) if model else None

    async def get_by_vnpay_txn_ref(self, txn_ref: str) -> Payment | None:
        """Fetch payment by VNPAY transaction reference"""
        stmt = select(PaymentModel).where(PaymentModel.vnpay_txn_ref == txn_ref)
        result = await self.session.execute(stmt)
        model = result.scalars().first()
        return self._to_entity(model) if model else None

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
        model = PaymentTransactionModel(
            payment_id=payment_id,
            appointment_id=appointment_id,
            transaction_type=transaction_type,
            amount=amount,
            currency=currency,
            provider_ref=provider_ref,
            response_code=response_code,
            metadata_json=metadata,
        )
        self.session.add(model)
        await self.session.flush()
        return self._to_transaction_entity(model)

    async def list_by_patient_id(self, patient_id: UUID) -> list[Payment]:
        """List all payments for a patient ordered by created_at desc"""
        stmt = (
            select(PaymentModel)
            .where(PaymentModel.patient_id == patient_id)
            .order_by(PaymentModel.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return [self._to_entity(m) for m in result.scalars().all()]

    async def list_transactions(self, payment_id: UUID) -> list[PaymentTransaction]:
        stmt = (
            select(PaymentTransactionModel)
            .where(PaymentTransactionModel.payment_id == payment_id)
            .order_by(PaymentTransactionModel.created_at.asc())
        )
        result = await self.session.execute(stmt)
        return [self._to_transaction_entity(model) for model in result.scalars().all()]

    async def _find_model(self, payment_id: UUID) -> PaymentModel | None:
        """Internal: find model by ID"""
        return await self.session.get(PaymentModel, payment_id)

    def _to_entity(self, model: PaymentModel) -> Payment:
        """Convert model to entity"""
        return Payment(
            id=model.id,
            appointment_id=model.appointment_id,
            patient_id=model.patient_id,
            doctor_id=model.doctor_id,
            amount=model.amount,
            currency=model.currency,
            status=PaymentStatus(model.status.value),
            vnpay_txn_ref=model.vnpay_txn_ref,
            vnpay_provider_ref=model.vnpay_provider_ref,
            payment_url=model.payment_url,
            paid_at=model.paid_at,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    def _to_transaction_entity(self, model: PaymentTransactionModel) -> PaymentTransaction:
        return PaymentTransaction(
            id=model.id,
            payment_id=model.payment_id,
            appointment_id=model.appointment_id,
            transaction_type=PaymentTransactionType(model.transaction_type.value),
            amount=model.amount,
            currency=model.currency,
            provider_ref=model.provider_ref,
            response_code=model.response_code,
            metadata=model.metadata_json,
            created_at=model.created_at,
        )
