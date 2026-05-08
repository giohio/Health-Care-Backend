"""
Unit tests for presentation/routes/all_labs.py — POST /analyze-all-labs

Heavy dependencies (openai, celery, infrastructure) are stubbed in sys.modules
before the route module is loaded so the unit tests stay lightweight.
"""
import sys
import importlib.util
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Stub heavy infra modules BEFORE importing the route
# ---------------------------------------------------------------------------
_mock_tasks_module = MagicMock()
_mock_tasks_module.analyze_all_labs_task = MagicMock()

# Register stubs so the lazy "from infrastructure.celery.tasks import ..." works
sys.modules.setdefault("celery", MagicMock())
sys.modules.setdefault("infrastructure", MagicMock())
sys.modules.setdefault("infrastructure.celery", MagicMock())
sys.modules["infrastructure.celery.tasks"] = _mock_tasks_module

# ---------------------------------------------------------------------------
# Load only the all_labs router module — skip presentation/routes/__init__.py
# ---------------------------------------------------------------------------
_route_file = Path(__file__).parents[2] / "presentation" / "routes" / "all_labs.py"
_spec = importlib.util.spec_from_file_location(
    "presentation.routes.all_labs_standalone", str(_route_file)
)
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)
router = _module.router


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_mock():
    """Reset the stubbed task mock between tests."""
    _mock_tasks_module.analyze_all_labs_task.reset_mock()
    _mock_tasks_module.analyze_all_labs_task.delay.reset_mock()
    yield


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_analyze_all_labs_enqueues_task_and_returns_202(client):
    response = client.post(
        "/analyze-all-labs",
        json={
            "appointment_id": "appt-001",
            "patient_id": "pat-001",
            "summary_id": "sum-001",
        },
        headers={"X-User-Role": "service"},
    )

    assert response.status_code == 202
    _mock_tasks_module.analyze_all_labs_task.delay.assert_called_once()

    call_args = _mock_tasks_module.analyze_all_labs_task.delay.call_args[0][0]
    assert call_args["appointment_id"] == "appt-001"
    assert call_args["patient_id"] == "pat-001"
    assert call_args["summary_id"] == "sum-001"


def test_analyze_all_labs_returns_queued_and_appointment_id(client):
    response = client.post(
        "/analyze-all-labs",
        json={"appointment_id": "A-99", "patient_id": "P-1", "summary_id": "S-1"},
        headers={"X-User-Role": "service"},
    )

    assert response.json()["appointment_id"] == "A-99"
    assert response.json()["queued"] is True


def test_analyze_all_labs_admin_role_allowed(client):
    response = client.post(
        "/analyze-all-labs",
        json={"appointment_id": "A-1", "patient_id": "P-1", "summary_id": "S-1"},
        headers={"X-User-Role": "admin"},
    )

    assert response.status_code == 202


def test_analyze_all_labs_doctor_role_forbidden(client):
    response = client.post(
        "/analyze-all-labs",
        json={"appointment_id": "A-1", "patient_id": "P-1", "summary_id": "S-1"},
        headers={"X-User-Role": "doctor"},
    )

    assert response.status_code == 403
    _mock_tasks_module.analyze_all_labs_task.delay.assert_not_called()


def test_analyze_all_labs_patient_role_forbidden(client):
    response = client.post(
        "/analyze-all-labs",
        json={"appointment_id": "A-1", "patient_id": "P-1", "summary_id": "S-1"},
        headers={"X-User-Role": "patient"},
    )

    assert response.status_code == 403


def test_analyze_all_labs_missing_fields_returns_422(client):
    # Missing summary_id
    response = client.post(
        "/analyze-all-labs",
        json={"appointment_id": "A-1", "patient_id": "P-1"},
        headers={"X-User-Role": "service"},
    )

    assert response.status_code == 422
    _mock_tasks_module.analyze_all_labs_task.delay.assert_not_called()


def test_analyze_all_labs_default_role_is_service_allowed(client):
    """No X-User-Role header — defaults to 'service' per route definition → 202."""
    response = client.post(
        "/analyze-all-labs",
        json={"appointment_id": "A-1", "patient_id": "P-1", "summary_id": "S-1"},
        # No X-User-Role header
    )

    assert response.status_code == 202
