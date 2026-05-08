import asyncio
from datetime import date

import httpx
import pytest
from fastapi import FastAPI
from presentation.dependencies import get_admin_chart_data_use_case, get_admin_stats_use_case
from presentation.routes.admin import router


class DummyStatsUseCase:
    def __init__(self):
        self.calls = []

    async def execute(self, **kwargs):
        await asyncio.sleep(0)
        self.calls.append(kwargs)
        return {
            "status": "success",
            "data": {
                "period": {"date_from": "2026-03-01", "date_to": "2026-03-31"},
                "total_appointments": 0,
                "total_revenue": 0,
                "by_status": {},
                "by_specialty": [],
                "completion_rate": 0.0,
                "cancellation_rate": 0.0,
            },
        }


class DummyChartUseCase:
    def __init__(self):
        self.calls = []

    async def execute(self, **kwargs):
        await asyncio.sleep(0)
        self.calls.append(kwargs)
        return {
            "status": "success",
            "data": {
                "metric": kwargs["metric"],
                "period": {"date_from": "2026-03-01", "date_to": "2026-03-31"},
                "data_points": [
                    {"date": "2026-03-01", "value": 1, "label": "01/03"},
                ],
                "total": 1,
                "peak_day": {"date": "2026-03-01", "value": 1},
            },
        }


def _build_app(stats_uc, chart_uc):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_admin_stats_use_case] = lambda: stats_uc
    app.dependency_overrides[get_admin_chart_data_use_case] = lambda: chart_uc
    return app


@pytest.mark.asyncio
async def test_admin_stats_requires_admin_role():
    app = _build_app(DummyStatsUseCase(), DummyChartUseCase())

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        r = await client.get("/admin/stats", headers={"X-User-Role": "patient"})

    assert r.status_code == 403


@pytest.mark.asyncio
async def test_admin_stats_passes_query_and_returns_payload():
    stats_uc = DummyStatsUseCase()
    app = _build_app(stats_uc, DummyChartUseCase())

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        r = await client.get(
            "/admin/stats",
            params={
                "range": "week",
                "date_from": str(date(2026, 3, 1)),
                "date_to": str(date(2026, 3, 7)),
            },
            headers={"X-User-Role": "admin"},
        )

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "success"
    assert body["data"]["total_appointments"] == 0
    assert stats_uc.calls[0]["range_type"] == "week"
    assert str(stats_uc.calls[0]["date_from"]) == "2026-03-01"
    assert str(stats_uc.calls[0]["date_to"]) == "2026-03-07"


@pytest.mark.asyncio
async def test_admin_chart_data_passes_query_and_returns_payload():
    chart_uc = DummyChartUseCase()
    app = _build_app(DummyStatsUseCase(), chart_uc)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        r = await client.get(
            "/admin/chart-data",
            params={"range": "quarter", "metric": "revenue"},
            headers={"X-User-Role": "admin"},
        )

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "success"
    assert body["data"]["metric"] == "revenue"
    assert chart_uc.calls[0] == {"range_type": "quarter", "metric": "revenue"}
