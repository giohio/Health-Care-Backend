"""
Integration coverage placeholders for expiry and refund event flows.

These flows depend on upstream producers:
- payment.check_expiry publish timing
- payment.refund_requested publish from cancellation/refund flow
"""

import pytest


@pytest.mark.skip(reason="Requires deterministic payment.check_expiry producer timing in integration stack")
async def test_payment_expiry_emits_payment_expired_event_and_cancels_appointment():
    # Pending until deterministic expiry-event trigger is exposed for integration tests.
    pass


@pytest.mark.skip(reason="Requires refund_requested event producer wiring in current stack")
async def test_payment_refund_requested_emits_payment_refunded_event():
    # Pending until refund_requested producer path is wired end-to-end.
    pass
