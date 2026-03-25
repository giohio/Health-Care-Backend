import asyncio
from datetime import date, time
from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from Domain.exceptions.domain_exceptions import (
    AppointmentNotFoundException,
    InvalidStatusTransitionError,
    SlotNotAvailableError,
    UnauthorizedActionError,
)
from Domain.value_objects.appointment_status import AppointmentStatus
from Domain.value_objects.payment_status import PaymentStatus
from healthai_common import SagaFailedError

from presentation import dependencies
from presentation.dependencies import get_appointment_repo, get_doctor_queue_use_case
from presentation.routes.appointments import router


def test_dependency_factories_smoke():
    session = object()
    cache = dependencies.get_cache_client()
    assert cache is dependencies.get_cache_client()
    assert dependencies.get_db_session(session) is session
    assert dependencies.get_appointment_repo(session) is not None
    assert dependencies.get_doctor_client(cache) is not None
    assert dependencies.get_lock_manager(cache) is not None
    assert dependencies.get_event_publisher() is not None
    assert dependencies.get_pricing_policy() is not None


def test_get_doctor_queue_requires_date_query():
    app = FastAPI()
    app.include_router(router)

    class DummyQueueUC:
        async def execute(self, *_args):
            await asyncio.sleep(0)
            return []

    app.dependency_overrides[get_doctor_queue_use_case] = lambda: DummyQueueUC()

    client = TestClient(app)
    r = client.get(f"/doctor/{uuid4()}/queue")
    assert r.status_code == 422


def test_get_appointment_by_id_not_found():
    app = FastAPI()
    app.include_router(router)

    class Repo:
        async def get_by_id(self, _id):
            await asyncio.sleep(0)
            return None

    app.dependency_overrides[get_appointment_repo] = lambda: Repo()

    client = TestClient(app)
    r = client.get(
        f"/{uuid4()}",
        headers={"X-User-Id": str(uuid4()), "X-User-Role": "patient"},
    )
    assert r.status_code == 404


def test_book_appointment_for_other_patient_forbidden():
    app = FastAPI()
    app.include_router(router)

    class DummyBookUC:
        async def execute(self, *_args, **_kwargs):
            await asyncio.sleep(0)
            return SimpleNamespace()

    from presentation.dependencies import get_book_appointment_use_case

    app.dependency_overrides[get_book_appointment_use_case] = lambda: DummyBookUC()

    client = TestClient(app)
    payload = {
        "patient_id": str(uuid4()),
        "doctor_id": str(uuid4()),
        "specialty_id": str(uuid4()),
        "appointment_date": str(date.today()),
        "start_time": time(8, 0).isoformat(),
        "appointment_type": "general",
    }
    r = client.post("/", json=payload, headers={"X-User-Id": str(uuid4())})
    assert r.status_code == 403


def test_get_doctor_queue_success_path():
    app = FastAPI()
    app.include_router(router)

    class DummyQueueUC:
        async def execute(self, *_args):
            await asyncio.sleep(0)
            return []

    app.dependency_overrides[get_doctor_queue_use_case] = lambda: DummyQueueUC()

    client = TestClient(app)
    r = client.get(f"/doctor/{uuid4()}/queue", params={"appointment_date": str(date.today())})
    assert r.status_code == 200
    assert r.json() == []


def test_cancel_confirm_decline_reschedule_complete_no_show_exception_mappings():
    app = FastAPI()
    app.include_router(router)

    class DummyUC:
        def __init__(self, exc):
            self.exc = exc

        async def execute(self, *_args, **_kwargs):
            await asyncio.sleep(0)
            raise self.exc

    from presentation.dependencies import (
        get_cancel_appointment_use_case,
        get_complete_appointment_use_case,
        get_confirm_appointment_use_case,
        get_decline_appointment_use_case,
        get_mark_no_show_use_case,
        get_reschedule_appointment_use_case,
    )

    app.dependency_overrides[get_cancel_appointment_use_case] = lambda: DummyUC(UnauthorizedActionError("no"))
    app.dependency_overrides[get_confirm_appointment_use_case] = lambda: DummyUC(AppointmentNotFoundException())
    app.dependency_overrides[get_decline_appointment_use_case] = lambda: DummyUC(InvalidStatusTransitionError("bad"))
    app.dependency_overrides[get_reschedule_appointment_use_case] = lambda: DummyUC(UnauthorizedActionError("no"))
    app.dependency_overrides[get_complete_appointment_use_case] = lambda: DummyUC(AppointmentNotFoundException())
    app.dependency_overrides[get_mark_no_show_use_case] = lambda: DummyUC(InvalidStatusTransitionError("bad"))

    client = TestClient(app)
    appt_id = str(uuid4())
    user_id = str(uuid4())

    r_cancel = client.put(
        f"/{appt_id}/cancel",
        json={"reason": "x"},
        headers={"X-User-Id": user_id, "X-User-Role": "patient"},
    )
    assert r_cancel.status_code == 403

    r_confirm = client.put(f"/{appt_id}/confirm", headers={"X-User-Id": user_id})
    assert r_confirm.status_code == 404

    r_decline = client.put(
        f"/{appt_id}/decline",
        json={"reason": "x"},
        headers={"X-User-Id": user_id},
    )
    assert r_decline.status_code == 400

    r_reschedule = client.put(
        f"/{appt_id}/reschedule",
        json={"new_date": str(date.today()), "new_time": "09:00:00"},
        headers={"X-User-Id": user_id},
    )
    assert r_reschedule.status_code == 403

    r_complete = client.put(f"/{appt_id}/complete", headers={"X-User-Id": user_id})
    assert r_complete.status_code == 404

    r_noshow = client.put(f"/{appt_id}/no-show", headers={"X-User-Id": user_id})
    assert r_noshow.status_code == 400


def test_book_appointment_success_and_exception_mappings():
    app = FastAPI()
    app.include_router(router)

    class DummyBookUC:
        def __init__(self, result=None, exc=None):
            self.result = result
            self.exc = exc

        async def execute(self, *_args, **_kwargs):
            await asyncio.sleep(0)
            if self.exc:
                raise self.exc
            return self.result

    from presentation.dependencies import get_book_appointment_use_case

    appointment = SimpleNamespace(
        id=uuid4(),
        patient_id=uuid4(),
        doctor_id=uuid4(),
        specialty_id=uuid4(),
        appointment_date=date.today(),
        start_time=time(9, 0),
        end_time=time(9, 30),
        appointment_type="general",
        chief_complaint=None,
        note_for_doctor=None,
        status=AppointmentStatus.PENDING_PAYMENT,
        payment_status=PaymentStatus.PROCESSING,
        queue_number=None,
    )

    client = TestClient(app)
    payload = {
        "patient_id": None,
        "doctor_id": str(appointment.doctor_id),
        "specialty_id": str(appointment.specialty_id),
        "appointment_date": str(date.today()),
        "start_time": "09:00:00",
        "appointment_type": "general",
    }

    app.dependency_overrides[get_book_appointment_use_case] = lambda: DummyBookUC(result=appointment)
    ok = client.post("/", json=payload, headers={"X-User-Id": str(appointment.patient_id)})
    assert ok.status_code == 200

    app.dependency_overrides[get_book_appointment_use_case] = lambda: DummyBookUC(
        exc=SlotNotAvailableError("slot taken")
    )
    conflict = client.post("/", json=payload, headers={"X-User-Id": str(appointment.patient_id)})
    assert conflict.status_code == 409

    app.dependency_overrides[get_book_appointment_use_case] = lambda: DummyBookUC(
        exc=SagaFailedError("step failed")
    )
    bad_request = client.post("/", json=payload, headers={"X-User-Id": str(appointment.patient_id)})
    assert bad_request.status_code == 400

    app.dependency_overrides[get_book_appointment_use_case] = lambda: DummyBookUC(
        exc=SagaFailedError("Slot is no longer available")
    )
    slot_conflict = client.post("/", json=payload, headers={"X-User-Id": str(appointment.patient_id)})
    assert slot_conflict.status_code == 409


def test_get_appointment_authorization_and_slots_endpoint():
    app = FastAPI()
    app.include_router(router)

    class Repo:
        def __init__(self, appointment):
            self.appointment = appointment

        async def get_by_id(self, _id):
            await asyncio.sleep(0)
            return self.appointment

    class SlotsUC:
        async def execute(self, **_kwargs):
            await asyncio.sleep(0)
            return {
                "date": date.today(),
                "doctor_id": uuid4(),
                "duration_minutes": 30,
                "slots": [
                    {
                        "start_time": "09:00:00",
                        "end_time": "09:30:00",
                        "is_available": True,
                        "reason": None,
                    }
                ],
                "error": None,
            }

    from presentation.dependencies import get_available_slots_use_case

    owner_id = uuid4()
    appointment = SimpleNamespace(
        id=uuid4(),
        patient_id=owner_id,
        doctor_id=uuid4(),
        specialty_id=uuid4(),
        appointment_date=date.today(),
        start_time=time(9, 0),
        end_time=time(9, 30),
        appointment_type="general",
        chief_complaint=None,
        note_for_doctor=None,
        status=AppointmentStatus.PENDING_PAYMENT,
        payment_status=PaymentStatus.PROCESSING,
        queue_number=1,
    )

    app.dependency_overrides[get_appointment_repo] = lambda: Repo(appointment)
    app.dependency_overrides[get_available_slots_use_case] = lambda: SlotsUC()

    client = TestClient(app)

    forbidden = client.get(
        f"/{appointment.id}",
        headers={"X-User-Id": str(uuid4()), "X-User-Role": "patient"},
    )
    assert forbidden.status_code == 403

    admin_ok = client.get(
        f"/{appointment.id}",
        headers={"X-User-Id": str(uuid4()), "X-User-Role": "admin"},
    )
    assert admin_ok.status_code == 200

    slots_ok = client.get(
        f"/doctor/{uuid4()}/slots",
        params={
            "appointment_date": str(date.today()),
            "specialty_id": str(uuid4()),
            "appointment_type": "general",
        },
    )
    assert slots_ok.status_code == 200
