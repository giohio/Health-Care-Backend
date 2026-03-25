"""
Pure helper functions for VNPAY signature generation and verification.
No side effects, no dependencies — easy to unit test.
"""

import hashlib
import hmac
import urllib.parse
from datetime import datetime, timedelta, timezone


def build_query_string(params: dict) -> str:
    """Sort params by key and encode to query string (VNPAY spec)."""
    # VNPAY recommends quote_plus or quote, but quote is safer for spaces -> %20
    return urllib.parse.urlencode(sorted(params.items()), quote_via=urllib.parse.quote_plus)


def sign(query_string: str, hash_secret: str) -> str:
    """HMAC-SHA512 signature."""
    return hmac.new(
        hash_secret.encode("utf-8"),
        query_string.encode("utf-8"),
        hashlib.sha512,
    ).hexdigest()


def generate_payment_url(
    *,
    tmn_code: str,
    hash_secret: str,
    vnpay_url: str,
    return_url: str,
    order_id: str,
    amount: int,  # VND nguyên (không nhân 100)
    order_desc: str,
    client_ip: str,
) -> str:
    # VNPAY yêu cầu múi giờ GMT+7 cho vnp_CreateDate và vnp_ExpireDate
    vn_timezone = timezone(timedelta(hours=7))
    current_time = datetime.now(vn_timezone)

    params = {
        "vnp_Version": "2.1.0",
        "vnp_Command": "pay",
        "vnp_TmnCode": tmn_code,
        "vnp_Amount": str(amount * 100),  # VNPAY yêu cầu * 100
        "vnp_CurrCode": "VND",
        "vnp_TxnRef": order_id,
        "vnp_OrderInfo": order_desc,
        "vnp_OrderType": "other",
        "vnp_Locale": "vn",
        "vnp_ReturnUrl": return_url,
        "vnp_IpAddr": client_ip,
        "vnp_CreateDate": current_time.strftime("%Y%m%d%H%M%S"),
        "vnp_ExpireDate": (current_time + timedelta(minutes=15)).strftime("%Y%m%d%H%M%S"),
    }

    # Lọc bỏ các giá trị trống
    params = {k: v for k, v in params.items() if v}

    query_string = build_query_string(params)
    signature = sign(query_string, hash_secret)
    return f"{vnpay_url}?{query_string}&vnp_SecureHash={signature}"


def verify_signature(params: dict, hash_secret: str) -> bool:
    """Verify IPN/return callback signature. Mutates a copy of params."""
    p = dict(params)
    received_hash = p.pop("vnp_SecureHash", "")
    p.pop("vnp_SecureHashType", None)

    # Lọc các value None/rỗng như lúc tạo
    p = {k: v for k, v in p.items() if v}

    query_string = build_query_string(p)
    expected = sign(query_string, hash_secret)
    return hmac.compare_digest(expected, received_hash)
