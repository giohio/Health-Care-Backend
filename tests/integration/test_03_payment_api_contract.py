"""
Integration: Payment API contract endpoints.
"""

import uuid

from tests.conftest import PAYMENT_URL


class TestPaymentApiContract:
    async def test_get_unknown_payment_returns_404(self, http, admin_token):
        missing_appointment_id = str(uuid.uuid4())
        resp = await http.get(
            f"{PAYMENT_URL}/payments/{missing_appointment_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 404

    async def test_vnpay_return_endpoint_exists(self, http):
        resp = await http.get(f"{PAYMENT_URL}/vnpay/return")
        assert resp.status_code == 302

    async def test_vnpay_ipn_endpoint_exists(self, http):
        resp = await http.get(f"{PAYMENT_URL}/vnpay/ipn")
        assert resp.status_code == 200
        body = resp.json()
        assert body.get("RspCode") in ("01", "97", "99")
