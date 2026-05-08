"""
E2E test suite: Clinical Service — diagnosis, medication, and clinical notes flow.

Covers:
  - Doctor creates a diagnosis for a patient
  - Doctor updates the diagnosis status
  - Doctor prescribes a medication
  - Doctor creates a clinical note
  - Patient retrieves their clinical summary
  - Role enforcement (patient cannot write)
"""

import asyncio
import base64
import json
import os
import uuid
from datetime import date

import httpx
import pytest

CLINICAL_URL = os.getenv("CLINICAL_URL", "http://localhost:8000/clinical")
AUTH_URL = os.getenv("AUTH_URL", "http://localhost:8000/auth")
DOCTOR_URL = os.getenv("DOCTOR_URL", "http://localhost:8000/doctors")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _decode_jwt(token: str) -> dict:
    parts = token.split(".")
    payload = parts[1] + "=" * (-len(parts[1]) % 4)
    return json.loads(base64.urlsafe_b64decode(payload.encode()).decode())


def doctor_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def patient_auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _wait_for_service(http: httpx.AsyncClient, url: str, wait_secs: int = 30) -> None:
    deadline = asyncio.get_running_loop().time() + wait_secs
    while asyncio.get_running_loop().time() < deadline:
        try:
            resp = await http.get(f"{url}/health")
            if resp.status_code == 200 and resp.json().get("service") == "clinical-service":
                return
        except Exception:
            pass
        await asyncio.sleep(1)
    pytest.skip(f"Clinical service not reachable at {url} — skipping E2E tests")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------




@pytest.fixture(scope="module")
async def doctor_token(http, admin_token):
    """Register a doctor user via admin and return dict with token and user_id."""
    email = f"e2e_doctor_{uuid.uuid4().hex[:8]}@healthai.dev"
    credential = "Doctor123!"
    r = await http.post(
        f"{AUTH_URL}/admin/register-staff",
        json={"email": email, "password": credential, "role": "doctor"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    if r.status_code not in (200, 201):
        pytest.skip(f"Doctor registration failed: {r.status_code}")
    r2 = await http.post(f"{AUTH_URL}/login", json={"email": email, "password": credential})
    assert r2.status_code == 200, f"Login failed: {r2.text}"
    token = r2.json()["access_token"]
    user_id = _decode_jwt(token)["user_id"]
    # Provision doctor aggregate
    await http.post(
        f"{DOCTOR_URL}/",
        json={"user_id": user_id, "full_name": f"Dr. ClinicalTest {uuid.uuid4().hex[:4]}"},
        headers={"Authorization": f"Bearer {token}"},
    )
    return {"token": token, "user_id": user_id}


@pytest.fixture(scope="module")
async def patient_token(http):
    """Register a patient user and return dict with token and user_id."""
    email = f"e2e_patient_{uuid.uuid4().hex[:8]}@healthai.dev"
    credential = "Patient123!"
    r = await http.post(f"{AUTH_URL}/register", json={"email": email, "password": credential})
    if r.status_code not in (200, 201):
        pytest.skip(f"Auth service not reachable: {r.status_code}")
    otp_resp = await http.get(f"{AUTH_URL}/dev/otp/{email}")
    if otp_resp.status_code == 200:
        otp = otp_resp.json().get("otp")
        if otp:
            await http.post(f"{AUTH_URL}/verify-email", json={"email": email, "otp": otp})
    r2 = await http.post(f"{AUTH_URL}/login", json={"email": email, "password": credential})
    assert r2.status_code == 200, f"Login failed: {r2.text}"
    token = r2.json()["access_token"]
    user_id = _decode_jwt(token)["user_id"]
    return {"token": token, "user_id": user_id}


# ---------------------------------------------------------------------------
# Test suite
# ---------------------------------------------------------------------------


@pytest.mark.e2e
class TestClinicalServiceE2E:
    """Full clinical flow E2E tests.

    These tests require:
    - clinical_service running and reachable at CLINICAL_URL
    - auth_service running for token issuance
    - Kong configured with /clinical route + JWT plugin
    """

    async def test_01_health_check(self, http):
        resp = await http.get(f"{CLINICAL_URL}/health")
        if resp.status_code != 200:
            pytest.skip("Clinical service health check failed — skipping E2E suite")
        assert resp.json()["service"] == "clinical-service"

    async def test_02_doctor_adds_diagnosis(self, http, doctor_token):
        patient_id = str(uuid.uuid4())
        doctor_id = doctor_token["user_id"]
        headers = doctor_headers(doctor_token["token"])

        resp = await http.post(
            f"{CLINICAL_URL}/patients/{patient_id}/diagnoses",
            headers=headers,
            json={
                "patient_id": patient_id,
                "doctor_id": doctor_id,
                "diagnosis_name": "Hypertension",
                "diagnosed_at": str(date.today()),
                "icd10_code": "I10",
            },
        )
        if resp.status_code in (401, 403, 503):
            pytest.skip(f"Service gateway issue: {resp.status_code}")

        assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data["diagnosis_name"] == "Hypertension"
        assert data["status"] == "active"

        return data["id"]

    async def test_03_doctor_updates_diagnosis(self, http, doctor_token):
        patient_id = str(uuid.uuid4())
        doctor_id = doctor_token["user_id"]
        headers = doctor_headers(doctor_token["token"])

        # First create
        r = await http.post(
            f"{CLINICAL_URL}/patients/{patient_id}/diagnoses",
            headers=headers,
            json={
                "patient_id": patient_id,
                "doctor_id": doctor_id,
                "diagnosis_name": "Type 2 Diabetes",
                "diagnosed_at": str(date.today()),
            },
        )
        if r.status_code in (401, 403, 503):
            pytest.skip(f"Service unavailable: {r.status_code}")
        assert r.status_code == 201
        diagnosis_id = r.json()["id"]

        # Now update
        r2 = await http.patch(
            f"{CLINICAL_URL}/patients/{patient_id}/diagnoses/{diagnosis_id}",
            headers=headers,
            json={"status": "resolved"},
        )
        assert r2.status_code == 200
        assert r2.json()["status"] == "resolved"

    async def test_04_doctor_prescribes_medication(self, http, doctor_token):
        patient_id = str(uuid.uuid4())
        doctor_id = doctor_token["user_id"]
        headers = doctor_headers(doctor_token["token"])

        resp = await http.post(
            f"{CLINICAL_URL}/patients/{patient_id}/medications",
            headers=headers,
            json={
                "patient_id": patient_id,
                "doctor_id": doctor_id,
                "drug_name": "Metformin 500mg",
                "start_date": str(date.today()),
                "dosage": "500mg",
                "frequency": "twice daily",
            },
        )
        if resp.status_code in (401, 403, 503):
            pytest.skip(f"Service unavailable: {resp.status_code}")
        assert resp.status_code == 201
        assert resp.json()["drug_name"] == "Metformin 500mg"
        assert resp.json()["status"] == "active"

    async def test_05_doctor_creates_clinical_note(self, http, doctor_token):
        patient_id = str(uuid.uuid4())
        doctor_id = doctor_token["user_id"]
        headers = doctor_headers(doctor_token["token"])

        resp = await http.post(
            f"{CLINICAL_URL}/patients/{patient_id}/notes",
            headers=headers,
            json={
                "patient_id": patient_id,
                "doctor_id": doctor_id,
                "content": "Patient presents with elevated blood pressure. Prescribed Amlodipine.",
                "note_type": "soap",
                "is_ai_generated": False,
            },
        )
        if resp.status_code in (401, 403, 503):
            pytest.skip(f"Service unavailable: {resp.status_code}")
        assert resp.status_code == 201
        assert resp.json()["note_type"] == "soap"

    async def test_06_doctor_lists_diagnoses(self, http, doctor_token):
        patient_id = str(uuid.uuid4())
        doctor_id = doctor_token["user_id"]
        headers = doctor_headers(doctor_token["token"])

        # Create a diagnosis first
        await http.post(
            f"{CLINICAL_URL}/patients/{patient_id}/diagnoses",
            headers=headers,
            json={
                "patient_id": patient_id,
                "doctor_id": doctor_id,
                "diagnosis_name": "Hyperlipidemia",
                "diagnosed_at": str(date.today()),
            },
        )

        resp = await http.get(
            f"{CLINICAL_URL}/patients/{patient_id}/diagnoses",
            headers=headers,
        )
        if resp.status_code in (401, 403, 503):
            pytest.skip(f"Service unavailable: {resp.status_code}")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    async def test_07_patient_can_access_own_summary(self, http, patient_token):
        patient_id = patient_token["user_id"]
        headers = patient_auth_header(patient_token["token"])

        resp = await http.get(
            f"{CLINICAL_URL}/patients/{patient_id}/summary",
            headers=headers,
        )
        if resp.status_code in (401, 503):
            pytest.skip(f"Service unavailable: {resp.status_code}")
        assert resp.status_code == 200
        data = resp.json()
        assert "diagnoses" in data
        assert "medications" in data
        assert "allergies" in data

    async def test_08_patient_denied_other_patient_summary(self, http, patient_token):
        other_patient_id = str(uuid.uuid4())
        headers = patient_auth_header(patient_token["token"])

        resp = await http.get(
            f"{CLINICAL_URL}/patients/{other_patient_id}/summary",
            headers=headers,
        )
        if resp.status_code == 503:
            pytest.skip("Service unavailable")
        assert resp.status_code == 403

    async def test_09_patient_cannot_add_diagnosis(self, http, patient_token):
        patient_id = patient_token["user_id"]
        headers = patient_auth_header(patient_token["token"])

        resp = await http.post(
            f"{CLINICAL_URL}/patients/{patient_id}/diagnoses",
            headers=headers,
            json={
                "patient_id": patient_id,
                "doctor_id": str(uuid.uuid4()),
                "diagnosis_name": "Self-diagnosed",
                "diagnosed_at": str(date.today()),
            },
        )
        if resp.status_code == 503:
            pytest.skip("Service unavailable")
        assert resp.status_code == 403
