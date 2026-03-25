import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.requests import Request

from presentation.dependencies import (
    get_event_publisher,
    get_get_payment_use_case,
    get_process_vnpay_ipn_use_case,
)
from presentation.routes.payments import router


class DummyProcessIpnUseCase:
    def __init__(self, *, result=None, exc=None):
        self.result = result or {"RspCode": "00", "Message": "OK"}
        self.exc = exc
        self.calls = []

    async def execute(self, params):
        await asyncio.sleep(0)
        self.calls.append(params)
        if self.exc is not None:
            raise self.exc
        return self.result


def _build_app(ipn_uc):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_get_payment_use_case] = lambda: SimpleNamespace()
    app.dependency_overrides[get_process_vnpay_ipn_use_case] = lambda: ipn_uc
    app.dependency_overrides[get_event_publisher] = lambda: SimpleNamespace()
    app.state.ipn_uc = ipn_uc
    return app


def test_vnpay_ipn_post_falls_back_to_raw_body_when_form_parse_fails(monkeypatch):
    async def broken_form(_self):
        await asyncio.sleep(0)
        raise RuntimeError("multipart unavailable")

    monkeypatch.setattr(Request, "form", broken_form)

    ipn_uc = DummyProcessIpnUseCase()
    app = _build_app(ipn_uc)
    client = TestClient(app)

    r = client.post("/vnpay/ipn?vnp_TxnRef=TQ", data="vnp_ResponseCode=00&x=1")

    assert r.status_code == 200
    assert r.json()["RspCode"] == "00"
    called = app.state.ipn_uc.calls[-1]
    assert called["vnp_TxnRef"] == "TQ"
    assert called["vnp_ResponseCode"] == "00"
    assert called["x"] == "1"


def test_vnpay_ipn_post_uses_form_items_when_parser_succeeds(monkeypatch):
    async def ok_form(_self):
        await asyncio.sleep(0)
        return {"vnp_ResponseCode": "00", "x": 1}

    monkeypatch.setattr(Request, "form", ok_form)

    ipn_uc = DummyProcessIpnUseCase()
    app = _build_app(ipn_uc)
    client = TestClient(app)

    r = client.post("/vnpay/ipn?vnp_TxnRef=TFORM")

    assert r.status_code == 200
    called = app.state.ipn_uc.calls[-1]
    assert called["vnp_TxnRef"] == "TFORM"
    assert called["vnp_ResponseCode"] == "00"
    assert called["x"] == "1"


def test_vnpay_ipn_returns_99_when_use_case_raises():
    ipn_uc = DummyProcessIpnUseCase(exc=RuntimeError("boom"))
    app = _build_app(ipn_uc)
    client = TestClient(app)

    r = client.get("/vnpay/ipn", params={"vnp_TxnRef": "ERR"})

    assert r.status_code == 200
    assert r.json() == {"RspCode": "99", "Message": "boom"}
