from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from Domain.interfaces import IEventPublisher, IPaymentProvider
from Domain.interfaces.payment_repository import IPaymentRepository
from Domain.value_objects.payment_transaction_type import PaymentTransactionType


class ProcessVNPayIPnUseCase:
    """Handle VNPAY IPN callback"""

    def __init__(
        self,
        session: Any,
        payment_repo: IPaymentRepository,
        payment_provider: IPaymentProvider,
        event_publisher: IEventPublisher,
    ):
        self.session = session
        self.payment_repo = payment_repo
        self.payment_provider = payment_provider
        self.event_publisher = event_publisher

    async def execute(self, params: dict) -> dict:
        """
        Process VNPAY IPN callback

        Args:
            params: Query parameters from VNPAY callback

        Returns: {RspCode: '00'|'xx', Message: str}
        """
        verify_result = self.payment_provider.verify_callback(params)
        if not verify_result.success and verify_result.failure_reason == "Invalid signature":
            return {"RspCode": "97", "Message": "Invalid signature"}

        # Get transaction reference
        txn_ref = params.get("vnp_TxnRef")
        if not txn_ref:
            return {"RspCode": "01", "Message": "Invalid TxnRef"}

        # Find payment by transaction reference
        payment = await self.payment_repo.get_by_vnpay_txn_ref(txn_ref)
        if not payment:
            return {"RspCode": "01", "Message": "Payment not found"}

        response_code = str(params.get("vnp_ResponseCode", ""))
        provider_ref = verify_result.provider_ref or params.get("vnp_TransactionNo")

        # Idempotency: already processed (IPN may have run before Return URL)
        from Domain.value_objects.payment_status import PaymentStatus
        if payment.status in (PaymentStatus.PAID, PaymentStatus.FAILED, PaymentStatus.EXPIRED):
            return {"RspCode": "02", "Message": "Order already confirmed"}

        if response_code == "00":
            payment.mark_as_paid(
                provider_ref=provider_ref or "",
                paid_at=datetime.now(timezone.utc),
            )
            await self.payment_repo.save(payment)
            await self.payment_repo.append_transaction(
                payment_id=payment.id,
                appointment_id=payment.appointment_id,
                transaction_type=PaymentTransactionType.PAYMENT_PAID,
                amount=payment.amount,
                currency=payment.currency,
                provider_ref=payment.vnpay_provider_ref,
                response_code=response_code,
                metadata={
                    "ipn": params,
                },
            )

            # Publish different events for lab order vs appointment payments
            if payment.payment_type == "LAB_ORDER_BUNDLE":
                transactions = await self.payment_repo.list_transactions(payment.id)
                lab_order_ids: list[str] = []
                for txn in transactions:
                    metadata = txn.metadata or {}
                    if metadata.get("source") == "bulk_lab_order_payment":
                        lab_order_ids = list(metadata.get("lab_order_ids") or [])
                        break

                child_payments = await self.payment_repo.list_by_reference_ids(
                    [UUID(str(order_id)) for order_id in lab_order_ids]
                )
                for child in child_payments:
                    child.mark_as_paid(
                        provider_ref=payment.vnpay_provider_ref or "",
                        paid_at=payment.paid_at,
                    )
                    await self.payment_repo.save(child)
                    await self.payment_repo.append_transaction(
                        payment_id=child.id,
                        appointment_id=child.appointment_id,
                        transaction_type=PaymentTransactionType.PAYMENT_PAID,
                        amount=child.amount,
                        currency=child.currency,
                        provider_ref=payment.vnpay_provider_ref,
                        response_code=response_code,
                        metadata={
                            "ipn": params,
                            "bundle_payment_id": str(payment.id),
                        },
                    )
                    await self.event_publisher.publish(
                        session=self.session,
                        aggregate_id=child.id,
                        aggregate_type="payment_events",
                        event_type="lab_payment.paid",
                        payload={
                            "payment_id": str(child.id),
                            "lab_order_id": str(child.reference_id),
                            "patient_id": str(child.patient_id),
                            "doctor_id": str(child.doctor_id),
                            "status": child.status.value,
                            "provider_ref": child.vnpay_provider_ref,
                        },
                    )
            elif payment.payment_type == "LAB_ORDER":
                await self.event_publisher.publish(
                    session=self.session,
                    aggregate_id=payment.id,
                    aggregate_type="payment_events",
                    event_type="lab_payment.paid",
                    payload={
                        "payment_id": str(payment.id),
                        "lab_order_id": str(payment.reference_id),
                        "patient_id": str(payment.patient_id),
                        "doctor_id": str(payment.doctor_id),
                        "status": payment.status.value,
                        "provider_ref": payment.vnpay_provider_ref,
                    },
                )
            else:
                await self.event_publisher.publish(
                    session=self.session,
                    aggregate_id=payment.id,
                    aggregate_type="payment_events",
                    event_type="payment.paid",
                    payload={
                        "payment_id": str(payment.id),
                        "appointment_id": str(payment.appointment_id),
                        "patient_id": str(payment.patient_id),
                        "doctor_id": str(payment.doctor_id),
                        "status": payment.status.value,
                        "provider_ref": payment.vnpay_provider_ref,
                    },
                )
            await self.session.commit()
            return {"RspCode": "00", "Message": "OK"}

        payment.mark_as_failed()
        payment.vnpay_provider_ref = provider_ref
        await self.payment_repo.save(payment)
        await self.payment_repo.append_transaction(
            payment_id=payment.id,
            appointment_id=payment.appointment_id,
            transaction_type=PaymentTransactionType.PAYMENT_FAILED,
            amount=payment.amount,
            currency=payment.currency,
            provider_ref=payment.vnpay_provider_ref,
            response_code=response_code,
            metadata={
                "ipn": params,
            },
        )

        await self.event_publisher.publish(
            session=self.session,
            aggregate_id=payment.id,
            aggregate_type="payment_events",
            event_type="payment.failed",
            payload={
                "payment_id": str(payment.id),
                "appointment_id": str(payment.appointment_id),
                "patient_id": str(payment.patient_id),
                "doctor_id": str(payment.doctor_id),
                "status": payment.status.value,
                "response_code": response_code,
                "provider_ref": payment.vnpay_provider_ref,
            },
        )
        await self.session.commit()
        return {"RspCode": "00", "Message": "Processed failed payment"}
