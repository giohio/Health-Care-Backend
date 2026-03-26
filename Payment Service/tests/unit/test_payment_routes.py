import asyncio
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from presentation.dependencies import get_event_publisher, get_get_payment_use_case, get_process_vnpay_ipn_use_case
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


class DummyProcessIpnUseCase:
    def __init__(self, result=None):
        self.result = result or {"RspCode": "00", "Message": "OK"}
        self.calls = []

    async def execute(self, params):
        await asyncio.sleep(0)
        self.calls.append(params)
        return self.result


@pytest.fixture
def app_with_overrides():
    app = FastAPI()
    app.include_router(router)

    get_payment_uc = DummyGetPaymentUseCase(payload={"id": "p-1", "status": "pending", "appointment_id": str(uuid4())})
    ipn_uc = DummyProcessIpnUseCase()

    app.dependency_overrides[get_get_payment_use_case] = lambda: get_payment_uc
    app.dependency_overrides[get_process_vnpay_ipn_use_case] = lambda: ipn_uc
    app.dependency_overrides[get_event_publisher] = lambda: SimpleNamespace()
    app.state.get_payment_uc = get_payment_uc
    app.state.ipn_uc = ipn_uc
    return app


def test_get_payment_success(app_with_overrides):
    client = TestClient(app_with_overrides)
    appt_id = str(uuid4())
    r = client.get(f"/payments/{appt_id}", headers={"X-User-Id": str(uuid4())})

    assert r.status_code == 200
    assert r.json()["id"] == "p-1"
    assert len(app_with_overrides.state.get_payment_uc.calls) == 1


def test_get_payment_not_found_maps_to_404():
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_get_payment_use_case] = lambda: DummyGetPaymentUseCase(exc=ValueError("missing"))
    app.dependency_overrides[get_process_vnpay_ipn_use_case] = lambda: DummyProcessIpnUseCase()
    app.dependency_overrides[get_event_publisher] = lambda: SimpleNamespace()

    client = TestClient(app)
    r = client.get(f"/payments/{uuid4()}", headers={"X-User-Id": str(uuid4())})

    assert r.status_code == 404
    assert r.json()["detail"] == "missing"


def test_vnpay_ipn_supports_get_and_passes_query(app_with_overrides):
    client = TestClient(app_with_overrides)
    r = client.get("/vnpay/ipn", params={"vnp_TxnRef": "T1", "vnp_ResponseCode": "00"})

    assert r.status_code == 200
    assert r.json()["RspCode"] == "00"
    assert app_with_overrides.state.ipn_uc.calls[-1]["vnp_TxnRef"] == "T1"


def test_vnpay_ipn_supports_post_and_merges_form(app_with_overrides):
    client = TestClient(app_with_overrides)
    r = client.post("/vnpay/ipn?vnp_TxnRef=TQ", data={"vnp_ResponseCode": "00", "x": "1"})

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
def test_vnpay_return_redirects_with_derived_status(app_with_overrides, params, expected_status):
    client = TestClient(app_with_overrides)
    r = client.get("/vnpay/return", params=params, follow_redirects=False)

    assert r.status_code == 302
    location = r.headers["location"]
    parsed = urlparse(location)
    qs = parse_qs(parsed.query)
    assert qs["status"][0] == expected_status
    assert qs["txn_ref"][0] == params.get("vnp_TxnRef", "")
