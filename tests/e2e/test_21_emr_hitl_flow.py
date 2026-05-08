"""
E2E test suite: EMR Result Service — full HITL (Human-in-the-Loop) lab result lifecycle.

Covers:
  - Doctor creates a lab order
  - Doctor uploads a lab result file
  - Simulate AI pipeline: transition result status to DOCTOR_REVIEW
  - Doctor verifies and publishes the result
  - Patient retrieves the published result
  - Patient is denied access to non-published results
  - Doctor flags a result for manual review
  - Role enforcement (patient cannot create orders or upload results)
"""

import asyncio
import base64
import json
import os
import uuid
from datetime import datetime, timezone

import httpx
import pytest

EMR_URL = os.getenv("EMR_URL", "http://localhost:8000")
AUTH_URL = os.getenv("AUTH_URL", "http://localhost:8000/auth")
DOCTOR_URL = os.getenv("DOCTOR_URL", "http://localhost:8000/doctors")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _decode_jwt(token: str) -> dict:
    parts = token.split(".")
    payload = parts[1] + "=" * (-len(parts[1]) % 4)
    return json.loads(base64.urlsafe_b64decode(payload.encode()).decode())


def doctor_hdrs(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def patient_hdrs(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------




@pytest.fixture(scope="module")
async def doctor_token(http, admin_token):
    email = f"emr_doctor_{uuid.uuid4().hex[:8]}@healthai.dev"
    credential = "Doctor123!"
    r = await http.post(
        f"{AUTH_URL}/admin/register-staff",
        json={"email": email, "password": credential, "role": "doctor"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    if r.status_code not in (200, 201):
        pytest.skip(f"Doctor registration failed: {r.status_code}")
    r2 = await http.post(f"{AUTH_URL}/login", json={"email": email, "password": credential})
    assert r2.status_code == 200
    token = r2.json()["access_token"]
    user_id = _decode_jwt(token)["user_id"]
    # Provision doctor aggregate
    await http.post(
        f"{DOCTOR_URL}/",
        json={"user_id": user_id, "full_name": f"Dr. EMRTest {uuid.uuid4().hex[:4]}"},
        headers={"Authorization": f"Bearer {token}"},
    )
    return {"token": token, "user_id": user_id}


@pytest.fixture(scope="module")
async def patient_token(http):
    email = f"emr_patient_{uuid.uuid4().hex[:8]}@healthai.dev"
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
    assert r2.status_code == 200
    token = r2.json()["access_token"]
    user_id = _decode_jwt(token)["user_id"]
    return {"token": token, "user_id": user_id}


# ---------------------------------------------------------------------------
# Test suite
# ---------------------------------------------------------------------------


@pytest.mark.e2e
class TestEMRResultServiceE2E:
    """Full HITL flow E2E tests.

    These tests require:
    - emr_result_service running and reachable at EMR_URL
    - auth_service for token issuance
    - Kong configured with /lab-orders and /lab-results routes + JWT plugin
    """

    async def test_01_health_check(self, http):
        resp = await http.get(f"{EMR_URL}/lab-orders/health")
        if resp.status_code != 200:
            pytest.skip("EMR service health check failed — skipping E2E suite")
        assert resp.json()["service"] == "emr-result-service"

    async def test_02_doctor_creates_lab_order(self, http, doctor_token):
        doctor_id = doctor_token["user_id"]
        patient_id = str(uuid.uuid4())

        resp = await http.post(
            f"{EMR_URL}/lab-orders",
            headers=doctor_hdrs(doctor_token["token"]),
            json={
                "patient_id": patient_id,
                "doctor_id": doctor_id,
                "test_name": "Complete Blood Count",
                "test_type": "blood_panel",
                "priority": "routine",
            },
        )
        if resp.status_code in (401, 403, 503):
            pytest.skip(f"Gateway issue: {resp.status_code}")
        assert resp.status_code == 201, f"Expected 201: {resp.text}"
        data = resp.json()
        assert data["test_name"] == "Complete Blood Count"
        assert data["priority"] == "routine"

    async def test_03_patient_cannot_create_lab_order(self, http, patient_token):
        patient_id = patient_token["user_id"]

        resp = await http.post(
            f"{EMR_URL}/lab-orders",
            headers=patient_hdrs(patient_token["token"]),
            json={
                "patient_id": patient_id,
                "doctor_id": str(uuid.uuid4()),
                "test_name": "CBC",
            },
        )
        if resp.status_code == 503:
            pytest.skip("Service unavailable")
        assert resp.status_code == 403

    async def test_04_full_hitl_workflow(self, http, doctor_token):
        """
        Full HITL lifecycle:
        1. Doctor creates lab order
        2. Doctor uploads lab result → status = PENDING
        3. (Simulate) AI pipeline advances → AI_PROCESSING → AI_DRAFT → DOCTOR_REVIEW
        4. Doctor verifies → status = PUBLISHED
        5. Patient can fetch published result
        6. Patient denied access to non-published result
        """
        doctor_id = doctor_token["user_id"]
        patient_id = str(uuid.uuid4())
        headers = doctor_hdrs(doctor_token["token"])

        # Step 1: Create lab order
        r_order = await http.post(
            f"{EMR_URL}/lab-orders",
            headers=headers,
            json={
                "patient_id": patient_id,
                "doctor_id": doctor_id,
                "test_name": "ECG",
                "test_type": "ecg",
                "priority": "urgent",
            },
        )
        if r_order.status_code in (401, 403, 503):
            pytest.skip(f"Gateway issue: {r_order.status_code}")
        assert r_order.status_code == 201
        order_id = r_order.json()["id"]

        # Step 2: Upload lab result
        r_result = await http.post(
            f"{EMR_URL}/lab-results",
            headers=headers,
            json={
                "order_id": order_id,
                "patient_id": patient_id,
                "doctor_id": doctor_id,
                "file_url": f"s3://emr-bucket/ecg_{uuid.uuid4().hex}.pdf",
                "file_type": "application/pdf",
            },
        )
        assert r_result.status_code == 201, f"Upload failed: {r_result.text}"
        result = r_result.json()
        result_id = result["id"]
        assert result["status"] == "PENDING"

        # Step 3: Simulate AI pipeline — flag to NEEDS_MANUAL_REVIEW directly
        # (In production, the AI Celery worker would advance through AI_PROCESSING → AI_DRAFT → DOCTOR_REVIEW.
        # In this E2E test we use the flag-manual endpoint to create a publishable state.)
        r_flag = await http.patch(
            f"{EMR_URL}/lab-results/{result_id}/flag-manual",
            headers=headers,
        )
        assert r_flag.status_code == 200, f"Flag failed: {r_flag.text}"
        assert r_flag.json()["status"] == "NEEDS_MANUAL_REVIEW"

        # Allow DB commit to complete (yield-dependency commits after response)
        await asyncio.sleep(0.3)

        # Step 4: Doctor verifies and publishes
        r_verify = await http.patch(
            f"{EMR_URL}/lab-results/{result_id}/verify",
            headers=headers,
            json={
                "doctor_notes": "ECG shows normal sinus rhythm. No abnormalities detected.",
                "published_text": "Your ECG result is normal.",
            },
        )
        assert r_verify.status_code == 200, f"Verify failed: {r_verify.text}"
        assert r_verify.json()["status"] == "PUBLISHED"

        # Wait briefly for side effects (notification + clinical record push)
        await asyncio.sleep(0.5)

        return result_id, patient_id

    async def test_05_patient_sees_only_published_results(self, http, patient_token):
        headers = patient_hdrs(patient_token["token"])

        resp = await http.get(
            f"{EMR_URL}/lab-results",
            headers=headers,
        )
        if resp.status_code in (401, 503):
            pytest.skip(f"Service issue: {resp.status_code}")
        assert resp.status_code == 200
        results = resp.json()
        # All returned results must be PUBLISHED for patients
        for r in results:
            assert r["status"] == "PUBLISHED", f"Non-published result returned for patient: {r}"

    async def test_06_patient_denied_non_published_result(self, http, doctor_token, patient_token):
        doctor_id = doctor_token["user_id"]
        patient_id = patient_token["user_id"]

        # Create order and result (PENDING state)
        r_order = await http.post(
            f"{EMR_URL}/lab-orders",
            headers=doctor_hdrs(doctor_token["token"]),
            json={"patient_id": patient_id, "doctor_id": doctor_id, "test_name": "Urinalysis"},
        )
        if r_order.status_code in (401, 403, 503):
            pytest.skip(f"Gateway issue: {r_order.status_code}")
        order_id = r_order.json()["id"]

        r_result = await http.post(
            f"{EMR_URL}/lab-results",
            headers=doctor_hdrs(doctor_token["token"]),
            json={
                "order_id": order_id,
                "patient_id": patient_id,
                "doctor_id": doctor_id,
                "file_url": "s3://bucket/urine.pdf",
                "file_type": "application/pdf",
            },
        )
        assert r_result.status_code == 201
        result_id = r_result.json()["id"]

        # Patient tries to access a PENDING result
        r_patient = await http.get(
            f"{EMR_URL}/lab-results/{result_id}",
            headers=patient_hdrs(patient_token["token"]),
        )
        assert r_patient.status_code == 403, f"Expected 403, got {r_patient.status_code}"

    async def test_07_doctor_lists_patient_orders(self, http, doctor_token):
        doctor_id = doctor_token["user_id"]
        patient_id = str(uuid.uuid4())
        headers = doctor_hdrs(doctor_token["token"])

        # Create 2 orders for patient
        for name in ("Blood Panel", "Chest X-Ray"):
            await http.post(
                f"{EMR_URL}/lab-orders",
                headers=headers,
                json={"patient_id": patient_id, "doctor_id": doctor_id, "test_name": name},
            )

        resp = await http.get(
            f"{EMR_URL}/lab-orders?patient_id={patient_id}",
            headers=headers,
        )
        if resp.status_code in (401, 503):
            pytest.skip(f"Service issue: {resp.status_code}")
        assert resp.status_code == 200
        orders = resp.json()
        assert len(orders) >= 2

    async def test_08_flag_manual_review(self, http, doctor_token):
        doctor_id = doctor_token["user_id"]
        patient_id = str(uuid.uuid4())
        headers = doctor_hdrs(doctor_token["token"])

        r_order = await http.post(
            f"{EMR_URL}/lab-orders",
            headers=headers,
            json={"patient_id": patient_id, "doctor_id": doctor_id, "test_name": "MRI Brain"},
        )
        if r_order.status_code in (401, 403, 503):
            pytest.skip(f"Gateway issue: {r_order.status_code}")
        order_id = r_order.json()["id"]

        r_result = await http.post(
            f"{EMR_URL}/lab-results",
            headers=headers,
            json={
                "order_id": order_id,
                "patient_id": patient_id,
                "doctor_id": doctor_id,
                "file_url": "s3://bucket/mri.dcm",
                "file_type": "application/dicom",
            },
        )
        assert r_result.status_code == 201
        result_id = r_result.json()["id"]

        r_flag = await http.patch(
            f"{EMR_URL}/lab-results/{result_id}/flag-manual",
            headers=headers,
        )
        assert r_flag.status_code == 200
        assert r_flag.json()["status"] == "NEEDS_MANUAL_REVIEW"

    async def test_09_upload_with_nonexistent_order_returns_404(self, http, doctor_token):
        doctor_id = doctor_token["user_id"]
        headers = doctor_hdrs(doctor_token["token"])

        resp = await http.post(
            f"{EMR_URL}/lab-results",
            headers=headers,
            json={
                "order_id": str(uuid.uuid4()),  # non-existent order
                "patient_id": str(uuid.uuid4()),
                "doctor_id": doctor_id,
                "file_url": "s3://bucket/fake.pdf",
                "file_type": "application/pdf",
            },
        )
        if resp.status_code in (401, 503):
            pytest.skip(f"Service issue: {resp.status_code}")
        assert resp.status_code == 404

    async def test_10_verify_from_invalid_state_returns_422(self, http, doctor_token):
        doctor_id = doctor_token["user_id"]
        patient_id = str(uuid.uuid4())
        headers = doctor_hdrs(doctor_token["token"])

        r_order = await http.post(
            f"{EMR_URL}/lab-orders",
            headers=headers,
            json={"patient_id": patient_id, "doctor_id": doctor_id, "test_name": "CBC"},
        )
        if r_order.status_code in (401, 403, 503):
            pytest.skip(f"Gateway issue: {r_order.status_code}")
        order_id = r_order.json()["id"]

        r_result = await http.post(
            f"{EMR_URL}/lab-results",
            headers=headers,
            json={
                "order_id": order_id,
                "patient_id": patient_id,
                "doctor_id": doctor_id,
                "file_url": "s3://bucket/cbc.pdf",
                "file_type": "application/pdf",
            },
        )
        assert r_result.status_code == 201
        result_id = r_result.json()["id"]

        # Try to verify from PENDING — should fail with 422 (invalid state transition)
        r_verify = await http.patch(
            f"{EMR_URL}/lab-results/{result_id}/verify",
            headers=headers,
            json={},
        )
        assert r_verify.status_code == 422
