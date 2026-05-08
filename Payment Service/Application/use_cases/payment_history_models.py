from dataclasses import dataclass, field


@dataclass
class PaymentHistoryItem:
    id: str
    appointment_id: str
    status: str
    appointment_status: str
    amount: int
    currency: str
    payment_url: str | None
    vnpay_txn_ref: str | None
    paid_at: str | None
    created_at: str | None
    patient_id: str | None = None
    doctor_id: str | None = None


@dataclass
class PaymentHistoryPage:
    items: list[PaymentHistoryItem] = field(default_factory=list)
    total: int = 0
    page: int = 1
    limit: int = 20
    total_pages: int = 0


def serialize_payment(payment, include_owner_fields: bool = False) -> PaymentHistoryItem:
    return PaymentHistoryItem(
        id=str(payment.id),
        appointment_id=str(payment.appointment_id),
        status=payment.status.value,
        appointment_status=payment.appointment_status,
        amount=payment.amount,
        currency=payment.currency,
        payment_url=payment.payment_url,
        vnpay_txn_ref=payment.vnpay_txn_ref,
        paid_at=payment.paid_at.isoformat() if payment.paid_at else None,
        created_at=payment.created_at.isoformat() if payment.created_at else None,
        patient_id=str(payment.patient_id) if include_owner_fields else None,
        doctor_id=str(payment.doctor_id) if include_owner_fields else None,
    )