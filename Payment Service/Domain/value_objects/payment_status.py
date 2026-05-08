from enum import Enum


class PaymentStatus(str, Enum):
    """Payment lifecycle states"""

    PENDING = "pending"
    PAID = "paid"
    FAILED = "failed"
    EXPIRED = "expired"
    REFUNDED = "refunded"
    REFUND_PENDING = "refund_pending"

    def __str__(self):
        return self.value
