from uuid import uuid4

import pytest

from Domain.interfaces import PaymentRequest
from infrastructure.providers.vnpay_provider import VnpayProvider


@pytest.mark.asyncio
async def test_create_payment_url_delegates_to_helper(monkeypatch):
    captured = {}

    def _fake_generate_payment_url(**kwargs):
        captured.update(kwargs)
        return "https://pay.test/checkout"

    import infrastructure.providers.vnpay_provider as provider_module

    monkeypatch.setattr(provider_module, "generate_payment_url", _fake_generate_payment_url)

    provider = VnpayProvider()
    request = PaymentRequest(
        order_id=uuid4(),
        amount=123456,
        order_desc="Pay appointment",
        return_url="https://frontend.test/return",
        client_ip="10.0.0.1",
    )

    url = await provider.create_payment_url(request)

    assert url == "https://pay.test/checkout"
    assert captured["order_id"] == str(request.order_id)
    assert captured["amount"] == request.amount
    assert captured["return_url"] == request.return_url
    assert captured["client_ip"] == request.client_ip


def test_verify_callback_invalid_signature_returns_failure(monkeypatch):
    import infrastructure.providers.vnpay_provider as provider_module

    monkeypatch.setattr(provider_module, "verify_signature", lambda *_: False)

    provider = VnpayProvider()
    result = provider.verify_callback({"vnp_ResponseCode": "00", "vnp_TransactionNo": "T1"})

    assert result.success is False
    assert result.provider_ref is None
    assert result.failure_reason == "Invalid signature"


def test_verify_callback_success_returns_provider_ref(monkeypatch):
    import infrastructure.providers.vnpay_provider as provider_module

    monkeypatch.setattr(provider_module, "verify_signature", lambda *_: True)

    provider = VnpayProvider()
    result = provider.verify_callback({"vnp_ResponseCode": "00", "vnp_TransactionNo": "T123"})

    assert result.success is True
    assert result.provider_ref == "T123"
    assert result.failure_reason is None


def test_verify_callback_non_00_response_returns_failure(monkeypatch):
    import infrastructure.providers.vnpay_provider as provider_module

    monkeypatch.setattr(provider_module, "verify_signature", lambda *_: True)

    provider = VnpayProvider()
    result = provider.verify_callback({"vnp_ResponseCode": "24", "vnp_TransactionNo": "T999"})

    assert result.success is False
    assert result.provider_ref == "T999"
    assert result.failure_reason == "VNPAY error code: 24"
