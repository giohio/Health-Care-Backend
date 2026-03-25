"""
Simulate VNPAY IPN callback for testing.
Constructs a valid signed IPN payload
and posts it to Payment Service.

This avoids needing real VNPAY sandbox
for unit-level integration tests.
"""

import hashlib
import hmac
import time
import urllib.parse

import httpx


class VNPaySimulator:
    def __init__(self, hash_secret: str, payment_url: str, ipn_path: str = "/vnpay/ipn"):
        self.hash_secret = hash_secret
        self.payment_url = payment_url
        self.ipn_path = ipn_path

    def _sign(self, params: dict) -> str:
        filtered = {k: v for k, v in params.items() if k not in ("vnp_SecureHash", "vnp_SecureHashType")}
        sorted_items = sorted(filtered.items())
        query = urllib.parse.urlencode(sorted_items)
        return hmac.new(self.hash_secret.encode("utf-8"), query.encode("utf-8"), hashlib.sha512).hexdigest()

    async def simulate_payment(
        self,
        http: httpx.AsyncClient,
        txn_ref: str,
        amount: int,
        success: bool = True,
    ) -> dict:
        """
        Send a signed IPN callback to Payment Service.
        success=True  → response_code='00' (paid)
        success=False → response_code='24' (cancelled)
        """
        response_code = "00" if success else "24"
        txn_no = f"VNP{int(time.time())}"

        params = {
            "vnp_TxnRef": txn_ref,
            "vnp_Amount": str(amount * 100),
            "vnp_ResponseCode": response_code,
            "vnp_TransactionNo": txn_no,
            "vnp_BankCode": "NCB",
            "vnp_PayDate": "20250319120000",
            "vnp_TransactionStatus": response_code,
            "vnp_OrderInfo": f"Test payment {txn_ref}",
        }
        params["vnp_SecureHash"] = self._sign(params)

        r = await http.get(f"{self.payment_url}{self.ipn_path}", params=params)
        return r.json()
