from urllib.parse import parse_qs, urlparse
from uuid import uuid4

from infrastructure.providers import vnpay_helper


def test_build_query_string_sorts_keys():
    qs = vnpay_helper.build_query_string({"b": "2", "a": "1"})
    assert qs == "a=1&b=2"


def test_sign_is_stable_and_hex():
    sig = vnpay_helper.sign("a=1&b=2", "secret")
    assert len(sig) == 128
    assert sig == vnpay_helper.sign("a=1&b=2", "secret")


def test_generate_payment_url_contains_signature_and_scaled_amount():
    url = vnpay_helper.generate_payment_url(
        tmn_code="TMN",
        hash_secret="SECRET",
        vnpay_url="https://sandbox.vnpayment.vn/pay",
        return_url="https://example.com/return",
        order_id=str(uuid4()),
        amount=650000,
        order_desc="Appointment payment",
        client_ip="127.0.0.1",
    )

    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    assert parsed.scheme == "https"
    assert "vnp_SecureHash" in query
    assert query["vnp_Amount"][0] == "65000000"
    assert query["vnp_Command"][0] == "pay"


def test_verify_signature_accepts_valid_signature_and_rejects_invalid():
    params = {
        "vnp_TxnRef": "ABC123",
        "vnp_ResponseCode": "00",
        "vnp_TransactionNo": "777",
    }
    qs = vnpay_helper.build_query_string(params)
    secure_hash = vnpay_helper.sign(qs, "SECRET")

    valid_payload = {**params, "vnp_SecureHash": secure_hash, "vnp_SecureHashType": "HmacSHA512"}
    invalid_payload = {**params, "vnp_SecureHash": "bad"}

    assert vnpay_helper.verify_signature(valid_payload, "SECRET") is True
    assert vnpay_helper.verify_signature(invalid_payload, "SECRET") is False
