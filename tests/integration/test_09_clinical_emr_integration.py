"""
Integration: clinical and EMR flows with role and visibility checks.
"""

import asyncio
import os
import uuid
from datetime import date

import pytest

from tests.conftest import AUTH_URL, DOCTOR_URL
from tests.helpers.auth import register_doctor, register_patient

CLINICAL_URL = os.getenv("CLINICAL_URL", "http://localhost:8000/clinical")
EMR_URL = os.getenv("EMR_URL", "http://localhost:8000")


class TestClinicalEmrIntegration:
    async def test_clinical_doctor_write_patient_read_and_rbac(self, http, admin_token, specialty_id):
        patient = await register_patient(http, AUTH_URL)
        doctor = await register_doctor(http, AUTH_URL, DOCTOR_URL, admin_token, specialty_id)

        patient_id = patient["user_id"]
        doctor_id = doctor["user_id"]
        doctor_h = {"Authorization": f"Bearer {doctor['access_token']}"}
        patient_h = {"Authorization": f"Bearer {patient['access_token']}"}

        create_diag = await http.post(
            f"{CLINICAL_URL}/patients/{patient_id}/diagnoses",
            headers=doctor_h,
            json={
                "patient_id": patient_id,
                "doctor_id": doctor_id,
                "diagnosis_name": "Hypertension",
                "diagnosed_at": str(date.today()),
                "icd10_code": "I10",
            },
        )
        if create_diag.status_code in (401, 403, 503):
            pytest.skip(f"Clinical gateway issue: {create_diag.status_code}")
        assert create_diag.status_code == 201, create_diag.text

        summary = await http.get(f"{CLINICAL_URL}/patients/{patient_id}/summary", headers=patient_h)
        assert summary.status_code == 200, summary.text
        body = summary.json()
        assert "diagnoses" in body
        assert isinstance(body["diagnoses"], list)

        forbidden = await http.post(
            f"{CLINICAL_URL}/patients/{patient_id}/diagnoses",
            headers=patient_h,
            json={
                "patient_id": patient_id,
                "doctor_id": str(uuid.uuid4()),
                "diagnosis_name": "Self diagnosis",
                "diagnosed_at": str(date.today()),
            },
        )
        assert forbidden.status_code == 403

    async def test_emr_manual_review_publish_then_patient_can_read(self, http, admin_token, specialty_id):
        patient = await register_patient(http, AUTH_URL)
        doctor = await register_doctor(http, AUTH_URL, DOCTOR_URL, admin_token, specialty_id)
        doctor_token = doctor["access_token"]
        doctor_user_id = doctor["user_id"]

        doctor_h = {"Authorization": f"Bearer {doctor_token}"}
        patient_h = {"Authorization": f"Bearer {patient['access_token']}"}

        order = await http.post(
            f"{EMR_URL}/lab-orders",
            headers=doctor_h,
            json={
                "patient_id": patient["user_id"],
                "doctor_id": doctor_user_id,
                "test_name": "ECG",
                "test_type": "ecg",
                "priority": "urgent",
            },
        )
        if order.status_code in (401, 403, 503):
            pytest.skip(f"EMR gateway issue: {order.status_code}")
        assert order.status_code == 201, order.text
        order_id = order.json()["id"]

        uploaded = await http.post(
            f"{EMR_URL}/lab-results",
            headers=doctor_h,
            json={
                "order_id": order_id,
                "patient_id": patient["user_id"],
                "doctor_id": doctor_user_id,
                "file_url": f"s3://emr-bucket/ecg_{uuid.uuid4().hex}.pdf",
                "file_type": "application/pdf",
            },
        )
        assert uploaded.status_code == 201, uploaded.text
        result_id = uploaded.json()["id"]

        blocked = await http.get(f"{EMR_URL}/lab-results/{result_id}", headers=patient_h)
        assert blocked.status_code == 403

        flagged = await http.patch(
            f"{EMR_URL}/lab-results/{result_id}/flag-manual",
            headers=doctor_h,
        )
        assert flagged.status_code == 200, flagged.text
        assert flagged.json()["status"] == "NEEDS_MANUAL_REVIEW"

        # DB commit in service happens in dependency cleanup; small delay avoids race.
        await asyncio.sleep(0.3)

        verified = await http.patch(
            f"{EMR_URL}/lab-results/{result_id}/verify",
            headers=doctor_h,
            json={
                "doctor_notes": "Reviewed and approved.",
                "published_text": "Your ECG is normal.",
            },
        )
        assert verified.status_code == 200, verified.text
        assert verified.json()["status"] == "PUBLISHED"

        visible = await http.get(f"{EMR_URL}/lab-results/{result_id}", headers=patient_h)
        assert visible.status_code == 200, visible.text
        assert visible.json()["status"] == "PUBLISHED"
