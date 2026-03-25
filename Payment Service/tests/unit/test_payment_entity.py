from datetime import datetime, timezone
from uuid import uuid4

from Domain.entities.payment import Payment
from Domain.value_objects.payment_status import PaymentStatus


def test_is_expired_returns_false_when_created_at_missing():
    payment = Payment(
        id=uuid4(),
        appointment_id=uuid4(),
        patient_id=uuid4(),
        doctor_id=uuid4(),
        amount=100000,
        status=PaymentStatus.PENDING,
        created_at=None,
    )

    assert payment.is_expired(datetime.now(timezone.utc)) is False
