import asyncio
from datetime import time
from types import SimpleNamespace
from uuid import uuid4

from Domain.exceptions.domain_exceptions import DoctorNotFoundException, SpecialtyAlreadyExistsException
from Domain.value_objects.day_of_week import DayOfWeek
from fastapi import FastAPI
from fastapi.testclient import TestClient
from presentation import dependencies
from presentation.dependencies import (
    get_db,
    get_doctor_repo,
    get_list_specialties_use_case,
    get_save_specialty_use_case,
    get_schedule_repo,
    get_search_available_doctors_use_case,
    get_set_auto_confirm_settings_use_case,
    get_update_doctor_profile_use_case,
    get_update_schedule_use_case,
)
from presentation.routes.doctors import router as doctors_router
from presentation.routes.schedules import router as schedules_router
from presentation.routes.specialties import router as specialties_router


def test_doctor_dependencies_smoke():
    session = object()
    specialty_repo = dependencies.get_specialty_repo(session)
    doctor_repo = dependencies.get_doctor_repo(session)
    schedule_repo = dependencies.get_schedule_repo(session)
    assert specialty_repo is not None
    assert doctor_repo is not None
    assert schedule_repo is not None
    assert dependencies.get_list_specialties_use_case(specialty_repo) is not None
    assert dependencies.get_save_specialty_use_case(specialty_repo) is not None
    assert dependencies.get_register_doctor_use_case(doctor_repo) is not None
    assert dependencies.get_update_schedule_use_case(schedule_repo, doctor_repo) is not None


def test_doctor_health_endpoint():
    app = FastAPI()
    app.include_router(doctors_router)
    client = TestClient(app)
    r = client.get("/health")
    assert r.status_code == 200


def test_provision_doctor_requires_admin():
    app = FastAPI()
    app.include_router(doctors_router)

    from presentation.dependencies import get_register_doctor_use_case

    class DummyUC:
        async def execute(self, *_args):
            await asyncio.sleep(0)

    app.dependency_overrides[get_register_doctor_use_case] = lambda: DummyUC()

    client = TestClient(app)
    payload = {"user_id": str(uuid4()), "full_name": "Dr. A"}
    r = client.post("/", json=payload, headers={"X-User-Role": "patient"})
    assert r.status_code == 403


def test_search_available_invalid_time_returns_400():
    app = FastAPI()
    app.include_router(doctors_router)

    from presentation.dependencies import get_search_available_doctors_use_case

    class DummyUC:
        async def execute(self, *_args):
            await asyncio.sleep(0)
            return []

    app.dependency_overrides[get_search_available_doctors_use_case] = lambda: DummyUC()

    client = TestClient(app)
    r = client.get(f"/search/available?specialty_id={uuid4()}&day=MONDAY&time=invalid")
    assert r.status_code == 400


def test_set_auto_confirm_requires_doctor_role():
    app = FastAPI()
    app.include_router(doctors_router)

    class DummyUC:
        async def execute(self, *_args, **_kwargs):
            await asyncio.sleep(0)
            return SimpleNamespace(
                user_id=uuid4(),
                auto_confirm=True,
                confirmation_timeout_minutes=10,
            )

    app.dependency_overrides[get_set_auto_confirm_settings_use_case] = lambda: DummyUC()

    client = TestClient(app)
    payload = {"auto_confirm": True, "confirmation_timeout_minutes": 10}
    r = client.put(
        "/me/auto-confirm",
        json=payload,
        headers={"X-User-Id": str(uuid4()), "X-User-Role": "patient"},
    )
    assert r.status_code == 403


def test_set_auto_confirm_exception_mappings():
    app = FastAPI()
    app.include_router(doctors_router)

    class NotFoundUC:
        async def execute(self, *_args, **_kwargs):
            await asyncio.sleep(0)
            raise DoctorNotFoundException(uuid4())

    class ValueErrorUC:
        async def execute(self, *_args, **_kwargs):
            await asyncio.sleep(0)
            raise ValueError("invalid")

    payload = {"auto_confirm": True, "confirmation_timeout_minutes": 10}
    user_id = str(uuid4())

    app.dependency_overrides[get_set_auto_confirm_settings_use_case] = lambda: NotFoundUC()
    client = TestClient(app)
    nf = client.put(
        "/me/auto-confirm",
        json=payload,
        headers={"X-User-Id": user_id, "X-User-Role": "doctor"},
    )
    assert nf.status_code == 404

    app.dependency_overrides[get_set_auto_confirm_settings_use_case] = lambda: ValueErrorUC()
    bad = client.put(
        "/me/auto-confirm",
        json=payload,
        headers={"X-User-Id": user_id, "X-User-Role": "doctor"},
    )
    assert bad.status_code == 400


def test_get_update_and_list_doctor_routes():
    app = FastAPI()
    app.include_router(doctors_router)

    class RepoNotFound:
        async def get_by_id(self, *_args):
            await asyncio.sleep(0)
            return None

        async def list_by_specialty(self, *_args):
            await asyncio.sleep(0)
            return []

    class RepoFound(RepoNotFound):
        async def get_by_id(self, user_id):
            await asyncio.sleep(0)
            return SimpleNamespace(
                user_id=user_id,
                full_name="Dr. A",
                specialty_id=None,
                title=None,
                experience_years=0,
                auto_confirm=True,
                confirmation_timeout_minutes=15,
            )

        async def list_by_specialty(self, specialty_id):
            await asyncio.sleep(0)
            return [
                SimpleNamespace(
                    user_id=uuid4(),
                    full_name="Dr. B",
                    specialty_id=specialty_id,
                    title="Cardio",
                    experience_years=3,
                    auto_confirm=True,
                    confirmation_timeout_minutes=15,
                )
            ]

    class UpdateNotFoundUC:
        async def execute(self, *_args, **_kwargs):
            await asyncio.sleep(0)
            raise DoctorNotFoundException(uuid4())

    class UpdateOkUC:
        async def execute(self, dto):
            await asyncio.sleep(0)
            return dto

    app.dependency_overrides[get_doctor_repo] = lambda: RepoNotFound()
    client = TestClient(app)
    user_id = str(uuid4())

    not_found = client.get(f"/{user_id}")
    assert not_found.status_code == 404

    app.dependency_overrides[get_doctor_repo] = lambda: RepoFound()
    ok = client.get(f"/{user_id}")
    assert ok.status_code == 200

    dto = {
        "user_id": str(uuid4()),
        "full_name": "Dr. X",
        "specialty_id": None,
        "title": None,
        "experience_years": 0,
        "auto_confirm": True,
        "confirmation_timeout_minutes": 15,
    }
    mismatch = client.put(f"/{uuid4()}", json=dto)
    assert mismatch.status_code == 400

    app.dependency_overrides[get_update_doctor_profile_use_case] = lambda: UpdateNotFoundUC()
    dto["user_id"] = str(uuid4())
    upd_not_found = client.put(f"/{dto['user_id']}", json=dto)
    assert upd_not_found.status_code == 404

    app.dependency_overrides[get_update_doctor_profile_use_case] = lambda: UpdateOkUC()
    upd_ok = client.put(f"/{dto['user_id']}", json=dto)
    assert upd_ok.status_code == 200

    by_specialty = client.get(f"/specialty/{uuid4()}")
    assert by_specialty.status_code == 200
    assert isinstance(by_specialty.json(), list)


def test_search_available_accepts_day_as_string_value():
    app = FastAPI()
    app.include_router(doctors_router)

    class DummyUC:
        async def execute(self, specialty_id, day, slot):
            await asyncio.sleep(0)
            return [
                {
                    "user_id": str(uuid4()),
                    "full_name": "Dr. C",
                    "specialty_id": specialty_id,
                    "title": None,
                    "experience_years": 1,
                    "auto_confirm": True,
                    "confirmation_timeout_minutes": 15,
                }
            ]

    app.dependency_overrides[get_search_available_doctors_use_case] = lambda: DummyUC()

    client = TestClient(app)
    r = client.get(f"/search/available?specialty_id={uuid4()}&day=MONDAY&time=09:30:00")
    assert r.status_code == 200


def test_schedules_and_specialties_routes_exception_mappings():
    app = FastAPI()
    app.include_router(schedules_router)
    app.include_router(specialties_router)

    class DummyDb:
        def __init__(self):
            self.commits = 0

        async def commit(self):
            await asyncio.sleep(0)
            self.commits += 1

    db = DummyDb()

    async def db_dep():
        yield db

    class ScheduleNotFoundUC:
        async def execute(self, *_args):
            await asyncio.sleep(0)
            raise DoctorNotFoundException(uuid4())

    class ScheduleOkUC:
        async def execute(self, doctor_id, dtos):
            await asyncio.sleep(0)
            return [
                SimpleNamespace(
                    id=uuid4(),
                    doctor_id=doctor_id,
                    day_of_week=DayOfWeek.MONDAY,
                    start_time=time(9, 0),
                    end_time=time(10, 0),
                    slot_duration_minutes=30,
                )
            ]

    class ScheduleRepo:
        async def list_by_doctor(self, doctor_id):
            await asyncio.sleep(0)
            return [
                SimpleNamespace(
                    id=uuid4(),
                    doctor_id=doctor_id,
                    day_of_week=DayOfWeek.MONDAY,
                    start_time=time(9, 0),
                    end_time=time(10, 0),
                    slot_duration_minutes=30,
                )
            ]

    class ListSpecialtiesUC:
        async def execute(self):
            await asyncio.sleep(0)
            return [SimpleNamespace(id=uuid4(), name="Cardiology", description="Heart")]

    class SaveSpecialtyErrUC:
        async def execute(self, _dto):
            await asyncio.sleep(0)
            raise SpecialtyAlreadyExistsException("Cardiology")

    class SaveSpecialtyOkUC:
        async def execute(self, _dto):
            await asyncio.sleep(0)
            return SimpleNamespace(id=uuid4(), name="Neuro", description=None)

    app.dependency_overrides[get_db] = db_dep
    app.dependency_overrides[get_schedule_repo] = lambda: ScheduleRepo()
    app.dependency_overrides[get_update_schedule_use_case] = lambda: ScheduleNotFoundUC()
    app.dependency_overrides[get_list_specialties_use_case] = lambda: ListSpecialtiesUC()
    app.dependency_overrides[get_save_specialty_use_case] = lambda: SaveSpecialtyErrUC()

    client = TestClient(app)
    doctor_id = str(uuid4())
    schedule_payload = [
        {
            "doctor_id": doctor_id,
            "day_of_week": 0,
            "start_time": "09:00:00",
            "end_time": "10:00:00",
            "slot_duration_minutes": 30,
        }
    ]

    sch_get = client.get(f"/{doctor_id}/schedule")
    assert sch_get.status_code == 200

    sch_nf = client.put(f"/{doctor_id}/schedule", json=schedule_payload)
    assert sch_nf.status_code == 404

    app.dependency_overrides[get_update_schedule_use_case] = lambda: ScheduleOkUC()
    sch_ok = client.put(f"/{doctor_id}/schedule", json=schedule_payload)
    assert sch_ok.status_code == 200
    assert db.commits == 1

    spec_list = client.get("/specialties")
    assert spec_list.status_code == 200

    spec_err = client.post("/specialties", json={"name": "Cardiology", "description": "Heart"})
    assert spec_err.status_code == 400

    app.dependency_overrides[get_save_specialty_use_case] = lambda: SaveSpecialtyOkUC()
    spec_ok = client.post("/specialties", json={"name": "Neuro", "description": None})
    assert spec_ok.status_code == 200
