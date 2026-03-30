import asyncio
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from presentation.dependencies import (
    get_event_publisher,
    get_generate_payment_url_use_case,
    get_get_payment_use_case,
    get_list_patient_payments_use_case,
    get_process_vnpay_ipn_use_case,
)
from presentation.routes.payments import router


class DummyGetPaymentUseCase:
    def __init__(self, payload=None, exc=None):
        self.payload = payload or {}
        self.exc = exc
        self.calls = []

    async def execute(self, appointment_id):
        await asyncio.sleep(0)
        self.calls.append(appointment_id)
        if self.exc:
            raise self.exc
        return self.payload


class DummyListPatientPaymentsUseCase:
    def __init__(self, result=None):
        self.result = result or []
        self.calls = []

    async def execute(self, patient_id):
        await asyncio.sleep(0)
        self.calls.append(patient_id)
        return self.result


class DummyProcessIpnUseCase:
    def __init__(self, result=None):
        self.result = result or {"RspCode": "00", "Message": "OK"}
        self.calls = []

    async def execute(self, params):
        await asyncio.sleep(0)
        self.calls.append(params)
        return self.result


class DummyGeneratePaymentUrlUseCase:
    def __init__(self, payload=None, exc=None):
        self.payload = payload or {
            "id": str(uuid4()),
            "appointment_id": str(uuid4()),
            "status": "pending",
            "amount": 500000,
            "currency": "VND",
            "payment_url": "https://sandbox.vnpayment.vn/paymentv2/vpcpay.html?test=1",
            "vnpay_txn_ref": str(uuid4()),
        }
        self.exc = exc
        self.calls = []

    async def execute(self, appointment_id, client_ip="127.0.0.1"):
        await asyncio.sleep(0)
        self.calls.append(appointment_id)
        if self.exc:
            raise self.exc
        return self.payload


@pytest.fixture
def app_with_overrides():
    app = FastAPI()
    app.include_router(router)

    get_payment_uc = DummyGetPaymentUseCase(payload={"id": "p-1", "status": "pending", "appointment_id": str(uuid4())})
    ipn_uc = DummyProcessIpnUseCase()
    gen_url_uc = DummyGeneratePaymentUrlUseCase()

    list_payments_uc = DummyListPatientPaymentsUseCase(result=[{"id": "pay-1", "status": "paid"}])

    app.dependency_overrides[get_get_payment_use_case] = lambda: get_payment_uc
    app.dependency_overrides[get_process_vnpay_ipn_use_case] = lambda: ipn_uc
    app.dependency_overrides[get_generate_payment_url_use_case] = lambda: gen_url_uc
    app.dependency_overrides[get_list_patient_payments_use_case] = lambda: list_payments_uc
    app.dependency_overrides[get_event_publisher] = lambda: SimpleNamespace()
    app.state.get_payment_uc = get_payment_uc
    app.state.ipn_uc = ipn_uc
    app.state.gen_url_uc = gen_url_uc
    app.state.list_payments_uc = list_payments_uc
    return app


@pytest.mark.asyncio
async def test_get_payment_success(app_with_overrides):
    transport = httpx.ASGITransport(app=app_with_overrides)
    appt_id = str(uuid4())
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        r = await client.get(f"/{appt_id}", headers={"X-User-Id": str(uuid4())})

    assert r.status_code == 200
    assert r.json()["id"] == "p-1"
    assert len(app_with_overrides.state.get_payment_uc.calls) == 1


@pytest.mark.asyncio
async def test_get_payment_not_found_maps_to_404():
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_get_payment_use_case] = lambda: DummyGetPaymentUseCase(exc=ValueError("missing"))
    app.dependency_overrides[get_process_vnpay_ipn_use_case] = lambda: DummyProcessIpnUseCase()
    app.dependency_overrides[get_event_publisher] = lambda: SimpleNamespace()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        r = await client.get(f"/{uuid4()}", headers={"X-User-Id": str(uuid4())})

    assert r.status_code == 404
    assert r.json()["detail"] == "missing"


@pytest.mark.asyncio
async def test_vnpay_ipn_supports_get_and_passes_query(app_with_overrides):
    transport = httpx.ASGITransport(app=app_with_overrides)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        r = await client.get("/vnpay/ipn", params={"vnp_TxnRef": "T1", "vnp_ResponseCode": "00"})

    assert r.status_code == 200
    assert r.json()["RspCode"] == "00"
    assert app_with_overrides.state.ipn_uc.calls[-1]["vnp_TxnRef"] == "T1"


@pytest.mark.asyncio
async def test_vnpay_ipn_supports_post_and_merges_form(app_with_overrides):
    transport = httpx.ASGITransport(app=app_with_overrides)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        r = await client.post("/vnpay/ipn?vnp_TxnRef=TQ", data={"vnp_ResponseCode": "00", "x": "1"})

    assert r.status_code == 200
    called = app_with_overrides.state.ipn_uc.calls[-1]
    assert called["vnp_TxnRef"] == "TQ"
    assert called["vnp_ResponseCode"] == "00"
    assert called["x"] == "1"


@pytest.mark.parametrize(
    "params,expected_status",
    [
        ({"vnp_ResponseCode": "00", "vnp_TransactionStatus": "00", "vnp_TxnRef": "A"}, "success"),
        ({"vnp_ResponseCode": "24", "vnp_TransactionStatus": "24", "vnp_TxnRef": "B"}, "failed"),
        ({"vnp_TxnRef": "C"}, "pending"),
    ],
)
@pytest.mark.asyncio
async def test_vnpay_return_redirects_with_derived_status(app_with_overrides, params, expected_status):
    transport = httpx.ASGITransport(app=app_with_overrides)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver", follow_redirects=False) as client:
        r = await client.get("/vnpay/return", params=params)

    assert r.status_code == 302
    location = r.headers["location"]
    parsed = urlparse(location)
    qs = parse_qs(parsed.query)
    assert qs["status"][0] == expected_status
    assert qs["txn_ref"][0] == params.get("vnp_TxnRef", "")


@pytest.mark.asyncio
async def test_post_pay_returns_payment_url(app_with_overrides):
    transport = httpx.ASGITransport(app=app_with_overrides)
    appt_id = str(uuid4())
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        r = await client.post(f"/{appt_id}/pay", headers={"X-User-Id": str(uuid4())})

    assert r.status_code == 200
    body = r.json()
    assert "payment_url" in body
    assert body["status"] == "pending"
    assert len(app_with_overrides.state.gen_url_uc.calls) == 1


@pytest.mark.asyncio
async def test_post_pay_not_found_returns_404(app_with_overrides):
    app_with_overrides.dependency_overrides[get_generate_payment_url_use_case] = lambda: DummyGeneratePaymentUrlUseCase(
        exc=ValueError("not found")
    )
    transport = httpx.ASGITransport(app=app_with_overrides)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        r = await client.post(f"/{uuid4()}/pay", headers={"X-User-Id": str(uuid4())})

    assert r.status_code == 404


@pytest.mark.asyncio
async def test_post_pay_already_paid_returns_409(app_with_overrides):
    app_with_overrides.dependency_overrides[get_generate_payment_url_use_case] = lambda: DummyGeneratePaymentUrlUseCase(
        exc=PermissionError("Cannot generate payment URL: payment is already 'paid'")
    )
    transport = httpx.ASGITransport(app=app_with_overrides)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        r = await client.post(f"/{uuid4()}/pay", headers={"X-User-Id": str(uuid4())})

    assert r.status_code == 409
    assert "paid" in r.json()["detail"]


@pytest.mark.asyncio
async def test_get_my_payments_returns_list(app_with_overrides):
    """GET /my returns the list of payments for the authenticated patient."""
    transport = httpx.ASGITransport(app=app_with_overrides)
    user_id = str(uuid4())
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        r = await client.get("/my", headers={"X-User-Id": user_id})

    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)
    assert body[0]["id"] == "pay-1"
    assert len(app_with_overrides.state.list_payments_uc.calls) == 1


@pytest.mark.asyncio
async def test_get_my_payments_missing_user_id_returns_422(app_with_overrides):
    """GET /my without X-User-Id header → 422 Unprocessable Entity."""
    transport = httpx.ASGITransport(app=app_with_overrides)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        r = await client.get("/my")

    assert r.status_code == 422


@pytest.mark.asyncio
async def test_get_my_payments_empty_list(app_with_overrides):
    """GET /my returns empty list when patient has no payments."""
    app_with_overrides.dependency_overrides[get_list_patient_payments_use_case] = (
        lambda: DummyListPatientPaymentsUseCase(result=[])
    )
    transport = httpx.ASGITransport(app=app_with_overrides)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        r = await client.get("/my", headers={"X-User-Id": str(uuid4())})

    assert r.status_code == 200
    assert r.json() == []
