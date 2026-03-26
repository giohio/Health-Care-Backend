import asyncio
from datetime import datetime
from datetime import time
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from Domain.exceptions.domain_exceptions import DoctorNotFoundException, SpecialtyAlreadyExistsException
from Domain.value_objects.day_of_week import DayOfWeek
from fastapi import FastAPI
from presentation import dependencies
from presentation.dependencies import (
    get_db,
    get_doctor_repo,
    get_list_specialties_use_case,
    get_register_doctor_use_case,
    get_save_specialty_use_case,
    get_schedule_repo,
    get_search_available_doctors_use_case,
    get_submit_rating_use_case,
    get_list_ratings_use_case,
    get_set_availability_use_case,
    get_get_availability_use_case,
    get_add_day_off_use_case,
    get_remove_day_off_use_case,
    get_list_service_offerings_use_case,
    get_add_service_offering_use_case,
    get_update_service_offering_use_case,
    get_deactivate_service_offering_use_case,
    get_enhanced_schedule_use_case,
    get_set_auto_confirm_settings_use_case,
    get_update_doctor_profile_use_case,
    get_update_schedule_use_case,
)
from presentation.routes.doctors import router as doctors_router
from presentation.routes.schedules import router as schedules_router
from presentation.routes.specialties import router as specialties_router


def _make_async_client(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver")


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


@pytest.mark.asyncio
async def test_doctor_health_endpoint():
    app = FastAPI()
    app.include_router(doctors_router)
    async with _make_async_client(app) as client:
        r = await client.get("/health")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_provision_doctor_requires_admin():
    app = FastAPI()
    app.include_router(doctors_router)

    from presentation.dependencies import get_register_doctor_use_case

    class DummyUC:
        async def execute(self, *_args):
            await asyncio.sleep(0)

    app.dependency_overrides[get_register_doctor_use_case] = lambda: DummyUC()

    payload = {"user_id": str(uuid4()), "full_name": "Dr. A"}
    async with _make_async_client(app) as client:
        r = await client.post("/", json=payload, headers={"X-User-Role": "patient"})
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_search_available_invalid_time_returns_400():
    app = FastAPI()
    app.include_router(doctors_router)

    from presentation.dependencies import get_search_available_doctors_use_case

    class DummyUC:
        async def execute(self, *_args):
            await asyncio.sleep(0)
            return []

    app.dependency_overrides[get_search_available_doctors_use_case] = lambda: DummyUC()

    async with _make_async_client(app) as client:
        r = await client.get(f"/search/available?specialty_id={uuid4()}&day=MONDAY&time=invalid")
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_set_auto_confirm_requires_doctor_role():
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

    payload = {"auto_confirm": True, "confirmation_timeout_minutes": 10}
    async with _make_async_client(app) as client:
        r = await client.put(
            "/me/auto-confirm",
            json=payload,
            headers={"X-User-Id": str(uuid4()), "X-User-Role": "patient"},
        )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_set_auto_confirm_exception_mappings():
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
    async with _make_async_client(app) as client:
        nf = await client.put(
            "/me/auto-confirm",
            json=payload,
            headers={"X-User-Id": user_id, "X-User-Role": "doctor"},
        )
    assert nf.status_code == 404

    app.dependency_overrides[get_set_auto_confirm_settings_use_case] = lambda: ValueErrorUC()
    async with _make_async_client(app) as client:
        bad = await client.put(
            "/me/auto-confirm",
            json=payload,
            headers={"X-User-Id": user_id, "X-User-Role": "doctor"},
        )
    assert bad.status_code == 400


@pytest.mark.asyncio
async def test_get_update_and_list_doctor_routes():
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
    user_id = str(uuid4())

    async with _make_async_client(app) as client:
        not_found = await client.get(f"/{user_id}")
    assert not_found.status_code == 404

    app.dependency_overrides[get_doctor_repo] = lambda: RepoFound()
    async with _make_async_client(app) as client:
        ok = await client.get(f"/{user_id}")
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
    async with _make_async_client(app) as client:
        mismatch = await client.put(f"/{uuid4()}", json=dto)
    assert mismatch.status_code == 400

    app.dependency_overrides[get_update_doctor_profile_use_case] = lambda: UpdateNotFoundUC()
    dto["user_id"] = str(uuid4())
    async with _make_async_client(app) as client:
        upd_not_found = await client.put(f"/{dto['user_id']}", json=dto)
    assert upd_not_found.status_code == 404

    app.dependency_overrides[get_update_doctor_profile_use_case] = lambda: UpdateOkUC()
    async with _make_async_client(app) as client:
        upd_ok = await client.put(f"/{dto['user_id']}", json=dto)
    assert upd_ok.status_code == 200

    async with _make_async_client(app) as client:
        by_specialty = await client.get(f"/specialty/{uuid4()}")
    assert by_specialty.status_code == 200
    assert isinstance(by_specialty.json(), list)


@pytest.mark.asyncio
async def test_search_available_accepts_day_as_string_value():
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

    async with _make_async_client(app) as client:
        r = await client.get(f"/search/available?specialty_id={uuid4()}&day=MONDAY&time=09:30:00")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_schedules_and_specialties_routes_exception_mappings():
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

    async with _make_async_client(app) as client:
        sch_get = await client.get(f"/{doctor_id}/schedule")
    assert sch_get.status_code == 200

    async with _make_async_client(app) as client:
        sch_nf = await client.put(f"/{doctor_id}/schedule", json=schedule_payload)
    assert sch_nf.status_code == 404

    app.dependency_overrides[get_update_schedule_use_case] = lambda: ScheduleOkUC()
    async with _make_async_client(app) as client:
        sch_ok = await client.put(f"/{doctor_id}/schedule", json=schedule_payload)
    assert sch_ok.status_code == 200
    assert db.commits == 1

    async with _make_async_client(app) as client:
        spec_list = await client.get("/specialties")
    assert spec_list.status_code == 200

    async with _make_async_client(app) as client:
        spec_err = await client.post("/specialties", json={"name": "Cardiology", "description": "Heart"})
    assert spec_err.status_code == 400

    app.dependency_overrides[get_save_specialty_use_case] = lambda: SaveSpecialtyOkUC()
    async with _make_async_client(app) as client:
        spec_ok = await client.post("/specialties", json={"name": "Neuro", "description": None})
    assert spec_ok.status_code == 200


@pytest.mark.asyncio
async def test_doctor_routes_cover_extended_branches():
    app = FastAPI()
    app.include_router(doctors_router)

    class RegisterUC:
        async def execute(self, *_args):
            await asyncio.sleep(0)

    class AutoConfirmUC:
        async def execute(self, **_kwargs):
            await asyncio.sleep(0)
            return SimpleNamespace(
                user_id=uuid4(),
                auto_confirm=True,
                confirmation_timeout_minutes=15,
            )

    class SearchUC:
        async def execute(self, specialty_id, day, slot):
            await asyncio.sleep(0)
            return [
                {
                    "user_id": str(uuid4()),
                    "full_name": "Dr. Search",
                    "specialty_id": specialty_id,
                    "title": "MD",
                    "experience_years": 2,
                    "auto_confirm": True,
                    "confirmation_timeout_minutes": 15,
                }
            ]

    class SubmitRatingUC:
        async def execute(self, *_args, **_kwargs):
            await asyncio.sleep(0)
            return SimpleNamespace(id=uuid4())

    class ListRatingsUC:
        async def execute(self, *_args):
            await asyncio.sleep(0)
            return [SimpleNamespace(rating=5, comment="great", created_at=datetime(2026, 3, 30, 9, 0, 0))]

    class SetAvailabilityUC:
        async def execute(self, *_args):
            await asyncio.sleep(0)

    class GetAvailabilityUC:
        async def execute(self, *_args):
            await asyncio.sleep(0)
            return [
                SimpleNamespace(
                    day_of_week=DayOfWeek.MONDAY,
                    start_time=time(9, 0),
                    end_time=time(10, 0),
                    max_patients=20,
                    break_start=None,
                    break_end=None,
                )
            ]

    class AddDayOffUC:
        async def execute(self, *_args):
            await asyncio.sleep(0)

    class RemoveDayOffUC:
        async def execute(self, *_args):
            await asyncio.sleep(0)

    class ListServicesUC:
        async def execute(self, *_args):
            await asyncio.sleep(0)
            return [SimpleNamespace(id=uuid4(), service_name="Consult", fee=100000.0, duration_minutes=30)]

    class AddServiceUC:
        async def execute(self, *_args):
            await asyncio.sleep(0)
            return SimpleNamespace(id=uuid4())

    class UpdateServiceUC:
        async def execute(self, *_args, **_kwargs):
            await asyncio.sleep(0)

    class DeactivateServiceUC:
        async def execute(self, *_args):
            await asyncio.sleep(0)

    class EnhancedScheduleUC:
        async def execute(self, *_args):
            await asyncio.sleep(0)
            return {"working_hours": [], "services": []}

    app.dependency_overrides[get_register_doctor_use_case] = lambda: RegisterUC()
    app.dependency_overrides[get_set_auto_confirm_settings_use_case] = lambda: AutoConfirmUC()
    app.dependency_overrides[get_search_available_doctors_use_case] = lambda: SearchUC()
    app.dependency_overrides[get_submit_rating_use_case] = lambda: SubmitRatingUC()
    app.dependency_overrides[get_list_ratings_use_case] = lambda: ListRatingsUC()
    app.dependency_overrides[get_set_availability_use_case] = lambda: SetAvailabilityUC()
    app.dependency_overrides[get_get_availability_use_case] = lambda: GetAvailabilityUC()
    app.dependency_overrides[get_add_day_off_use_case] = lambda: AddDayOffUC()
    app.dependency_overrides[get_remove_day_off_use_case] = lambda: RemoveDayOffUC()
    app.dependency_overrides[get_list_service_offerings_use_case] = lambda: ListServicesUC()
    app.dependency_overrides[get_add_service_offering_use_case] = lambda: AddServiceUC()
    app.dependency_overrides[get_update_service_offering_use_case] = lambda: UpdateServiceUC()
    app.dependency_overrides[get_deactivate_service_offering_use_case] = lambda: DeactivateServiceUC()
    app.dependency_overrides[get_enhanced_schedule_use_case] = lambda: EnhancedScheduleUC()

    doctor_id = str(uuid4())
    specialty_id = str(uuid4())
    service_id = str(uuid4())

    async with _make_async_client(app) as client:
        ok_provision = await client.post(
            "/",
            json={"user_id": str(uuid4()), "full_name": "Dr. Admin"},
            headers={"X-User-Role": "admin"},
        )
        assert ok_provision.status_code == 200

        auto_confirm_unauth = await client.put(
            "/me/auto-confirm",
            json={"auto_confirm": True, "confirmation_timeout_minutes": 15},
            headers={"X-User-Role": "doctor"},
        )
        assert auto_confirm_unauth.status_code == 401

        search_numeric_day_string = await client.get(
            f"/search/available?specialty_id={specialty_id}&day=2&time=09:30:00"
        )
        assert search_numeric_day_string.status_code == 200

        missing_user_rating = await client.post(f"/{doctor_id}/ratings?rating=5")
        assert missing_user_rating.status_code == 401

        create_rating = await client.post(
            f"/{doctor_id}/ratings?rating=5&comment=ok",
            headers={"X-User-Id": str(uuid4())},
        )
        assert create_rating.status_code == 200
        assert create_rating.json()["success"] is True

        list_ratings = await client.get(f"/{doctor_id}/ratings?page=1&limit=10")
        assert list_ratings.status_code == 200
        assert len(list_ratings.json()["ratings"]) == 1

        set_availability = await client.post(
            f"/{doctor_id}/availability?day_of_week=0&start_time=09:00:00&end_time=10:00:00"
        )
        assert set_availability.status_code == 200

        get_availability = await client.get(f"/{doctor_id}/availability")
        assert get_availability.status_code == 200
        assert len(get_availability.json()["items"]) == 1

        add_day_off = await client.post(f"/{doctor_id}/days-off?off_date=2026-03-30&reason=trip")
        assert add_day_off.status_code == 200

        remove_day_off = await client.delete(f"/{doctor_id}/days-off/2026-03-30")
        assert remove_day_off.status_code == 200

        list_services = await client.get(f"/{doctor_id}/services")
        assert list_services.status_code == 200
        assert len(list_services.json()["services"]) == 1

        add_service = await client.post(
            f"/{doctor_id}/services?service_name=Consult&duration_minutes=30&fee=100000&description=Basic"
        )
        assert add_service.status_code == 200

        update_service = await client.put(
            f"/{doctor_id}/services/{service_id}?service_name=Followup&duration_minutes=20"
        )
        assert update_service.status_code == 200

        delete_service = await client.delete(f"/{doctor_id}/services/{service_id}")
        assert delete_service.status_code == 200

        enhanced = await client.get(f"/{doctor_id}/schedule-enhanced?date=2026-03-30")
        assert enhanced.status_code == 200
