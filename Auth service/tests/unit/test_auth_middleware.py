import asyncio

import pytest
from fastapi import Request
from presentation.middleware import ExceptionMiddleware, RequestLogMiddleware
from starlette.responses import Response


@pytest.mark.asyncio
async def test_request_log_middleware_adds_process_time_header():
    mw = RequestLogMiddleware(app=None)

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/x",
        "headers": [],
        "query_string": b"",
        "client": ("127.0.0.1", 1234),
        "server": ("test", 80),
        "scheme": "http",
        "http_version": "1.1",
    }
    request = Request(scope)

    async def call_next(_request):
        await asyncio.sleep(0)
        return Response("ok", status_code=200)

    response = await mw.dispatch(request, call_next)
    assert response.status_code == 200
    assert "X-Process-Time" in response.headers


@pytest.mark.asyncio
async def test_exception_middleware_handles_error(monkeypatch):
    mw = ExceptionMiddleware(app=None)

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/x",
        "headers": [],
        "query_string": b"",
        "client": ("127.0.0.1", 1234),
        "server": ("test", 80),
        "scheme": "http",
        "http_version": "1.1",
    }
    request = Request(scope)

    from infrastructure import config as config_module

    monkeypatch.setattr(config_module.settings, "DEBUG", False)

    async def call_next(_request):
        raise RuntimeError("boom")

    response = await mw.dispatch(request, call_next)
    assert response.status_code == 500
