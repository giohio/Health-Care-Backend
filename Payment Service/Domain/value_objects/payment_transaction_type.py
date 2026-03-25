from enum import Enum


class PaymentTransactionType(str, Enum):
    PAYMENT_CREATED = "payment_created"
    PAYMENT_PAID = "payment_paid"
    PAYMENT_FAILED = "payment_failed"
    PAYMENT_EXPIRED = "payment_expired"
    REFUND_REQUESTED = "refund_requested"
    PAYMENT_REFUNDED = "payment_refunded"

    def __str__(self):
        return self.value
