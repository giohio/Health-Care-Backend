"""
Test suite: Payment expiry scenarios.
"""


class TestPaymentExpired:
    """
    Placeholder for payment timeout/expiry tests.
    Require a way to trigger payment.timeout/expired events.
    """

    async def test_payment_timeout_cancels_appointment(self, http, admin_token, specialty_id):
        """
        GIVEN a booking in pending_payment
        AND payment timeout expires (e.g., 15 min)
        WHEN timeout consumer processes payment.timeout
        THEN appointment status → cancelled
        AND patient notified
        """
        # This typically requires:
        # 1. Trigger a booking (pending_payment)
        # 2. Wait for payment service to emit payment.timeout
        # OR mock/seed a timeout event
        # 3. Verify appointment transitions to cancelled
