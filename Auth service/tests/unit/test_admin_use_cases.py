import asyncio
from datetime import datetime, time, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from Application.use_cases.get_system_config import GetSystemConfigUseCase
from Application.use_cases.list_users import ListUsersUseCase
from Application.use_cases.update_user_status import UpdateUserStatusUseCase
from Application.use_cases.upsert_system_config import UpsertSystemConfigUseCase


class FakeSystemConfigRepo:
    def __init__(self, current=None, updated=None):
        self.current = current
        self.updated = updated
        self.upsert_calls = []

    async def get(self):
        await asyncio.sleep(0)
        return self.current

    async def upsert(self, **fields):
        await asyncio.sleep(0)
        self.upsert_calls.append(fields)
        return self.updated


class FakeCountResult:
    def __init__(self, value):
        self.value = value

    def scalar(self):
        return self.value


class FakeUsersResult:
    def __init__(self, users):
        self.users = users

    def scalars(self):
        return self

    def all(self):
        return self.users


class FakeSession:
    def __init__(self, execute_results):
        self.execute_results = list(execute_results)
        self.execute_calls = 0
        self.flushed = 0

    async def execute(self, _query):
        await asyncio.sleep(0)
        idx = self.execute_calls
        self.execute_calls += 1
        return self.execute_results[idx]

    async def flush(self):
        await asyncio.sleep(0)
        self.flushed += 1


def _cfg_obj(**overrides):
    base = {
        "clinic_name": "HealthAI Clinic",
        "maintenance_mode": False,
        "default_slot_duration_minutes": 30,
        "max_appointments_per_day": 50,
        "support_email": "support@healthai.vn",
        "working_hours_start": time(8, 0),
        "working_hours_end": time(17, 0),
        "updated_at": datetime(2026, 4, 1, 8, 0, tzinfo=timezone.utc),
        "updated_by": uuid4(),
    }
    base.update(overrides)
    return SimpleNamespace(**base)


@pytest.mark.asyncio
async def test_get_system_config_use_case_formats_time_and_ids():
    cfg = _cfg_obj()
    use_case = GetSystemConfigUseCase(config_repo=FakeSystemConfigRepo(current=cfg))

    result = await use_case.execute()

    assert result["clinic_name"] == "HealthAI Clinic"
    assert result["working_hours_start"] == "08:00"
    assert result["working_hours_end"] == "17:00"
    assert result["updated_at"].startswith("2026-04-01T08:00:00")
    assert isinstance(result["updated_by"], str)


@pytest.mark.asyncio
async def test_upsert_system_config_rejects_invalid_slot_duration():
    repo = FakeSystemConfigRepo(current=_cfg_obj(), updated=_cfg_obj())
    use_case = UpsertSystemConfigUseCase(config_repo=repo)

    with pytest.raises(ValueError, match="default_slot_duration_minutes"):
        await use_case.execute(default_slot_duration_minutes=10)


@pytest.mark.asyncio
async def test_upsert_system_config_rejects_invalid_max_appointments():
    repo = FakeSystemConfigRepo(current=_cfg_obj(), updated=_cfg_obj())
    use_case = UpsertSystemConfigUseCase(config_repo=repo)

    with pytest.raises(ValueError, match="max_appointments_per_day"):
        await use_case.execute(max_appointments_per_day=0)


@pytest.mark.asyncio
async def test_upsert_system_config_rejects_inverted_partial_working_hours():
    current = _cfg_obj(working_hours_start=time(8, 0), working_hours_end=time(17, 0))
    repo = FakeSystemConfigRepo(current=current, updated=current)
    use_case = UpsertSystemConfigUseCase(config_repo=repo)

    with pytest.raises(ValueError, match="working_hours_start must be before working_hours_end"):
        await use_case.execute(working_hours_start=time(18, 0))


@pytest.mark.asyncio
async def test_upsert_system_config_success_serializes_output():
    updated_by = uuid4()
    updated = _cfg_obj(
        clinic_name="Clinic A",
        maintenance_mode=True,
        default_slot_duration_minutes=45,
        max_appointments_per_day=120,
        support_email="ops@healthai.vn",
        working_hours_start=time(9, 0),
        working_hours_end=time(18, 0),
        updated_by=updated_by,
    )
    repo = FakeSystemConfigRepo(current=_cfg_obj(), updated=updated)
    use_case = UpsertSystemConfigUseCase(config_repo=repo)

    result = await use_case.execute(
        updated_by=updated_by,
        clinic_name="Clinic A",
        maintenance_mode=True,
        default_slot_duration_minutes=45,
        max_appointments_per_day=120,
        support_email="ops@healthai.vn",
        working_hours_start=time(9, 0),
        working_hours_end=time(18, 0),
    )

    assert repo.upsert_calls, "Expected repository upsert to be called"
    assert result["clinic_name"] == "Clinic A"
    assert result["maintenance_mode"] is True
    assert result["default_slot_duration_minutes"] == 45
    assert result["working_hours_start"] == "09:00"
    assert result["working_hours_end"] == "18:00"
    assert result["updated_by"] == str(updated_by)


@pytest.mark.asyncio
async def test_list_users_use_case_shapes_response_and_caps_limit():
    user_1 = SimpleNamespace(
        id=uuid4(),
        email="alpha@healthai.dev",
        role="patient",
        is_active=True,
        is_email_verified=True,
        is_profile_completed=False,
        created_at=datetime(2026, 1, 10, tzinfo=timezone.utc),
    )
    user_2 = SimpleNamespace(
        id=uuid4(),
        email="beta@healthai.dev",
        role="doctor",
        is_active=False,
        is_email_verified=True,
        is_profile_completed=True,
        created_at=datetime(2026, 1, 11, tzinfo=timezone.utc),
    )
    session = FakeSession(execute_results=[FakeCountResult(2), FakeUsersResult([user_1, user_2])])
    use_case = ListUsersUseCase(session=session)

    result = await use_case.execute(role="patient", search="alpha", is_active=True, page=1, limit=500)

    assert result["total"] == 2
    assert result["limit"] == 100
    assert result["page"] == 1
    assert result["total_pages"] == 1
    assert len(result["users"]) == 2
    assert result["users"][0]["email"] == "alpha@healthai.dev"
    assert isinstance(result["users"][0]["id"], str)


@pytest.mark.asyncio
async def test_update_user_status_rejects_admin_self_change():
    session = FakeSession(execute_results=[])
    use_case = UpdateUserStatusUseCase(session=session)

    caller = uuid4()
    with pytest.raises(ValueError, match="cannot change their own"):
        await use_case.execute(user_id=caller, is_active=False, caller_id=caller)


@pytest.mark.asyncio
async def test_update_user_status_raises_not_found_when_missing_user():
    class EmptyResult:
        def scalar_one_or_none(self):
            return None

    session = FakeSession(execute_results=[EmptyResult()])
    use_case = UpdateUserStatusUseCase(session=session)

    with pytest.raises(LookupError, match="User not found"):
        await use_case.execute(user_id=uuid4(), is_active=False, caller_id=uuid4())


@pytest.mark.asyncio
async def test_update_user_status_updates_user_and_flushes():
    user = SimpleNamespace(
        id=uuid4(),
        email="u@healthai.dev",
        role="patient",
        is_active=True,
        is_email_verified=True,
        is_profile_completed=False,
        created_at=datetime(2026, 2, 1, tzinfo=timezone.utc),
    )

    class UserResult:
        def __init__(self, obj):
            self.obj = obj

        def scalar_one_or_none(self):
            return self.obj

    session = FakeSession(execute_results=[UserResult(user)])
    use_case = UpdateUserStatusUseCase(session=session)

    result = await use_case.execute(user_id=user.id, is_active=False, caller_id=uuid4())

    assert user.is_active is False
    assert session.flushed == 1
    assert result["is_active"] is False
    assert result["email"] == "u@healthai.dev"
