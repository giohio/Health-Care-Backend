"""
Integration: patient profile extensions and clinical vaccinations contracts.
"""

import os

import pytest

from tests.conftest import AUTH_URL, PATIENT_URL
from tests.helpers.auth import register_patient

CLINICAL_URL = os.getenv("CLINICAL_URL", "http://localhost:8000/clinical")


class TestPatientProfileExtensionsIntegration:
    async def test_patient_profile_patch_photo_and_vaccinations_empty(self, http, admin_token):
        patient = await register_patient(http, AUTH_URL)
        headers = {"Authorization": f"Bearer {patient['access_token']}"}

        patch_resp = await http.patch(
            f"{PATIENT_URL}/profile",
            headers=headers,
            json={
                "full_name": "Integration Patient",
                "vital_signs": {
                    "height_cm": 171.2,
                    "weight_kg": 67.8,
                    "blood_pressure": "120/80",
                    "heart_rate_bpm": 71,
                },
                "emergency_contact": {
                    "name": "Nguoi than",
                    "relationship": "Sibling",
                    "phone": "0909123456",
                    "email": "relative@example.com",
                },
                "insurance": {
                    "type": "BHYT_PUBLIC",
                    "card_number": "AB 1234567890",
                    "registered_hospital": "Benh vien Bach Mai",
                    "expiry_date": "2030-01-01",
                },
            },
        )
        if patch_resp.status_code in (401, 403, 503):
            pytest.skip(f"Patient gateway issue: {patch_resp.status_code}")
        assert patch_resp.status_code == 200, patch_resp.text
        assert patch_resp.json()["insurance"]["type"] == "BHYT_PUBLIC"

        photo_resp = await http.post(
            f"{PATIENT_URL}/profile/photo",
            headers=headers,
            files={"photo": ("avatar.png", b"image-bytes", "image/png")},
        )
        assert photo_resp.status_code == 200, photo_resp.text
        assert photo_resp.json()["profile_photo_url"]

        get_resp = await http.get(f"{PATIENT_URL}/profile", headers=headers)
        assert get_resp.status_code == 200, get_resp.text
        body = get_resp.json()
        assert body["profile"]["profile_photo_url"]
        assert body["profile"]["vital_signs"]["blood_pressure"] == "120/80"

        vaccinations = await http.get(
            f"{CLINICAL_URL}/patients/{patient['user_id']}/vaccinations",
            headers=headers,
        )
        if vaccinations.status_code in (401, 403, 503):
            pytest.skip(f"Clinical gateway issue: {vaccinations.status_code}")
        assert vaccinations.status_code == 200, vaccinations.text
        assert isinstance(vaccinations.json(), list)