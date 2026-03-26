import asyncio
from datetime import datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI
from presentation import dependencies
from presentation.dependencies import (
    get_current_user_id,
    get_event_publisher,
    get_health_repo,
    get_initialize_profile_use_case,
    get_latest_vitals_use_case,
    get_profile_repo,
    get_record_vitals_use_case,
    get_vitals_history_use_case,
    get_vitals_repo,
)
from presentation.routes.patient import router


class FakeProfileRepo:
    def __init__(self, fail=False):
        self.fail = fail
        self.profile = None

    async def get_by_user_id(self, user_id):
        await asyncio.sleep(0)
        if self.fail:
            raise ValueError("profile fail")
        return self.profile

    async def create(self, profile):
        await asyncio.sleep(0)
        # Route response schema expects built-in UUID, not custom UUID7.
        profile.id = UUID(str(profile.id))
        self.profile = profile
        return profile

    async def update(self, profile_id, **fields):
        await asyncio.sleep(0)
        if self.fail:
            raise ValueError("update fail")
        for key, value in fields.items():
            if hasattr(self.profile, key):
                setattr(self.profile, key, value)
        return self.profile


class FakeHealthRepo:
    def __init__(self, fail=False):
        self.fail = fail
        self.health = None

    async def get_by_patient_id(self, patient_id):
        await asyncio.sleep(0)
        if self.fail:
            raise ValueError("health fail")
        return self.health

    async def create(self, health):
        await asyncio.sleep(0)
        self.health = health
        return health

    async def update(self, patient_id, **fields):
        await asyncio.sleep(0)
        if self.fail:
            raise ValueError("update health fail")
        for key, value in fields.items():
            if hasattr(self.health, key):
                setattr(self.health, key, value)
        return self.health


class FakeVitalsUseCase:
    async def execute(self, *_args, **_kwargs):
        await asyncio.sleep(0)
        return SimpleNamespace(
            id=uuid4(),
            height_cm=170.0,
            weight_kg=65.5,
            blood_pressure_systolic=120,
            blood_pressure_diastolic=80,
            heart_rate=72,
            temperature_celsius=36.8,
            recorded_at=datetime(2026, 3, 30, 9, 0, 0),
        )


class FakeLatestVitalsUseCase:
    def __init__(self, result):
        self.result = result

    async def execute(self, *_args, **_kwargs):
        await asyncio.sleep(0)
        return self.result


class FakeHistoryVitalsUseCase:
    async def execute(self, *_args, **_kwargs):
        await asyncio.sleep(0)
        return [
            SimpleNamespace(
                id=uuid4(),
                height_cm=170.0,
                weight_kg=65.5,
                blood_pressure_systolic=120,
                blood_pressure_diastolic=80,
                heart_rate=72,
                temperature_celsius=36.8,
                recorded_at=datetime(2026, 3, 30, 9, 0, 0),
            )
        ]


def _build_app():
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.mark.asyncio
async def test_patient_dependency_factories_smoke():
    session = object()

    assert get_profile_repo(session) is not None
    assert get_health_repo(session) is not None
    assert get_event_publisher(session) is not None

    vitals_repo = get_vitals_repo(session)
    assert vitals_repo is not None

    init_uc = get_initialize_profile_use_case(get_profile_repo(session), get_health_repo(session))
    assert init_uc is not None

    record_uc = get_record_vitals_use_case(vitals_repo, session, init_uc)
    assert record_uc is not None

    latest_uc = get_latest_vitals_use_case(vitals_repo, init_uc)
    assert latest_uc is not None

    history_uc = get_vitals_history_use_case(vitals_repo, init_uc)
    assert history_uc is not None


def test_get_current_user_id_success_and_401_cases():
    uid = uuid4()
    assert get_current_user_id(str(uid)) == uid

    with pytest.raises(Exception):
        get_current_user_id("not-a-uuid")


@pytest.mark.asyncio
async def test_patient_routes_profile_health_and_summary_success_paths():
    app = _build_app()
    user_id = uuid4()

    app.dependency_overrides[dependencies.get_current_user_id] = lambda: user_id
    app.dependency_overrides[dependencies.get_profile_repo] = lambda: FakeProfileRepo()
    app.dependency_overrides[dependencies.get_health_repo] = lambda: FakeHealthRepo()
    app.dependency_overrides[dependencies.get_event_publisher] = lambda: SimpleNamespace(publish=FakeVitalsUseCase().execute)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        prof = await client.get("/")
        assert prof.status_code == 200

        upd_profile = await client.put("/profile", json={"full_name": "Alice"})
        assert upd_profile.status_code == 200

        upd_health = await client.put("/health", json={"height_cm": 170, "weight_kg": 65.5})
        assert upd_health.status_code == 200

        summary = await client.get("/health-summary")
        assert summary.status_code == 200


@pytest.mark.asyncio
async def test_patient_routes_value_error_paths_map_to_404():
    app = _build_app()
    user_id = uuid4()

    app.dependency_overrides[dependencies.get_current_user_id] = lambda: user_id
    app.dependency_overrides[dependencies.get_profile_repo] = lambda: FakeProfileRepo(fail=True)
    app.dependency_overrides[dependencies.get_health_repo] = lambda: FakeHealthRepo(fail=True)
    app.dependency_overrides[dependencies.get_event_publisher] = lambda: SimpleNamespace(publish=FakeVitalsUseCase().execute)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        get_fail = await client.get("/")
        assert get_fail.status_code == 404

        profile_fail = await client.put("/profile", json={"full_name": "Alice"})
        assert profile_fail.status_code == 404

        health_fail = await client.put("/health", json={"height_cm": 170})
        assert health_fail.status_code == 404


@pytest.mark.asyncio
async def test_patient_routes_vitals_endpoints_branches():
    app = _build_app()
    patient_id = uuid4()
    user_id = uuid4()

    app.dependency_overrides[dependencies.get_current_user_id] = lambda: user_id
    app.dependency_overrides[dependencies.get_record_vitals_use_case] = lambda: FakeVitalsUseCase()
    app.dependency_overrides[dependencies.get_latest_vitals_use_case] = lambda: FakeLatestVitalsUseCase(None)
    app.dependency_overrides[dependencies.get_vitals_history_use_case] = lambda: FakeHistoryVitalsUseCase()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        record = await client.post(
            f"/{patient_id}/vitals?height_cm=170&weight_kg=65.5&blood_pressure_systolic=120&blood_pressure_diastolic=80"
        )
        assert record.status_code == 200

        latest_unauth = await client.get(f"/{patient_id}/vitals/latest")
        assert latest_unauth.status_code == 401

        latest_forbidden = await client.get(
            f"/{patient_id}/vitals/latest",
            headers={"X-User-Id": str(uuid4()), "X-User-Role": "patient"},
        )
        assert latest_forbidden.status_code == 403

        latest_none = await client.get(
            f"/{patient_id}/vitals/latest",
            headers={"X-User-Id": str(patient_id), "X-User-Role": "patient"},
        )
        assert latest_none.status_code == 200
        assert latest_none.json() is None

        app.dependency_overrides[dependencies.get_latest_vitals_use_case] = lambda: FakeLatestVitalsUseCase(
            SimpleNamespace(
                height_cm=170.0,
                weight_kg=65.5,
                blood_pressure_systolic=120,
                blood_pressure_diastolic=80,
                heart_rate=72,
                temperature_celsius=36.8,
                recorded_at=datetime(2026, 3, 30, 9, 0, 0),
            )
        )
        latest_ok = await client.get(
            f"/{patient_id}/vitals/latest",
            headers={"X-User-Id": str(uuid4()), "X-User-Role": "doctor"},
        )
        assert latest_ok.status_code == 200

        history = await client.get(f"/{patient_id}/vitals?page=1&limit=20")
        assert history.status_code == 200
        assert isinstance(history.json(), list)
