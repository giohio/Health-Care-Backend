from datetime import date, datetime, time, timedelta, timezone
from uuid import UUID

from Domain.entities.payment import Payment
from Domain.entities.payment_transaction import PaymentTransaction
from Domain.interfaces.payment_repository import IPaymentRepository
from Domain.value_objects.payment_status import PaymentStatus
from Domain.value_objects.payment_transaction_type import PaymentTransactionType
from infrastructure.database.models import PaymentModel, PaymentTransactionModel
from sqlalchemy import func, select
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
            model.appointment_status = payment.appointment_status
        else:
            # Create new
            model = PaymentModel(
                id=payment.id,
                appointment_id=payment.appointment_id,
                patient_id=payment.patient_id,
                doctor_id=payment.doctor_id,
                amount=payment.amount,
                currency=payment.currency,
                payment_type=payment.payment_type,
                reference_id=payment.reference_id,
                status=payment.status,
                appointment_status=payment.appointment_status,
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

    async def update_appointment_status(
        self, appointment_id: UUID, appointment_status: str
    ) -> None:
        """Update cached appointment_status on the payment record for this appointment."""
        from sqlalchemy import update as sql_update

        stmt = (
            sql_update(PaymentModel)
            .where(PaymentModel.appointment_id == appointment_id)
            .values(appointment_status=appointment_status)
        )
        await self.session.execute(stmt)
        await self.session.flush()

    async def list_by_patient_id(self, patient_id: UUID) -> list[Payment]:
        """List all payments for a patient ordered by created_at desc"""
        stmt = (
            select(PaymentModel)
            .where(PaymentModel.patient_id == patient_id)
            .order_by(PaymentModel.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return [self._to_entity(m) for m in result.scalars().all()]

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
        filters = self._build_history_filters(
            from_date=from_date,
            to_date=to_date,
            status=status,
            patient_id=patient_id,
        )
        stmt = (
            select(PaymentModel)
            .where(*filters)
            .order_by(PaymentModel.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        count_stmt = select(func.count()).select_from(PaymentModel).where(*filters)
        result = await self.session.execute(stmt)
        count_result = await self.session.execute(count_stmt)
        return [self._to_entity(model) for model in result.scalars().all()], count_result.scalar_one()

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
        filters = self._build_history_filters(
            from_date=from_date,
            to_date=to_date,
            status=status,
            patient_id=patient_id,
            doctor_id=doctor_id,
        )
        stmt = (
            select(PaymentModel)
            .where(*filters)
            .order_by(PaymentModel.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        count_stmt = select(func.count()).select_from(PaymentModel).where(*filters)
        result = await self.session.execute(stmt)
        count_result = await self.session.execute(count_stmt)
        return [self._to_entity(model) for model in result.scalars().all()], count_result.scalar_one()

    async def list_transactions(self, payment_id: UUID) -> list[PaymentTransaction]:
        stmt = (
            select(PaymentTransactionModel)
            .where(PaymentTransactionModel.payment_id == payment_id)
            .order_by(PaymentTransactionModel.created_at.asc())
        )
        result = await self.session.execute(stmt)
        return [self._to_transaction_entity(model) for model in result.scalars().all()]

    async def get_by_reference_id(self, reference_id: UUID) -> Payment | None:
        """Fetch LAB_ORDER payment by reference_id (= lab_order_id)."""
        stmt = select(PaymentModel).where(
            PaymentModel.reference_id == reference_id,
            PaymentModel.payment_type == "LAB_ORDER",
        )
        result = await self.session.execute(stmt)
        model = result.scalars().first()
        return self._to_entity(model) if model else None

    async def _find_model(self, payment_id: UUID) -> PaymentModel | None:
        """Internal: find model by ID"""
        return await self.session.get(PaymentModel, payment_id)

    def _build_history_filters(
        self,
        *,
        from_date: date | None = None,
        to_date: date | None = None,
        status: str | None = None,
        patient_id: UUID | None = None,
        doctor_id: UUID | None = None,
    ) -> list:
        filters = []
        if patient_id is not None:
            filters.append(PaymentModel.patient_id == patient_id)
        if doctor_id is not None:
            filters.append(PaymentModel.doctor_id == doctor_id)
        if status is not None:
            filters.append(PaymentModel.status == status)
        if from_date is not None:
            filters.append(PaymentModel.created_at >= self._start_of_day(from_date))
        if to_date is not None:
            filters.append(PaymentModel.created_at < self._start_of_next_day(to_date))
        return filters

    def _start_of_day(self, value: date) -> datetime:
        return datetime.combine(value, time.min, tzinfo=timezone.utc)

    def _start_of_next_day(self, value: date) -> datetime:
        return self._start_of_day(value) + timedelta(days=1)

    def _to_entity(self, model: PaymentModel) -> Payment:
        """Convert model to entity"""
        return Payment(
            id=model.id,
            appointment_id=model.appointment_id,
            patient_id=model.patient_id,
            doctor_id=model.doctor_id,
            amount=model.amount,
            currency=model.currency,
            payment_type=model.payment_type,
            reference_id=model.reference_id,
            status=PaymentStatus(model.status.value),
            appointment_status=model.appointment_status,
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
