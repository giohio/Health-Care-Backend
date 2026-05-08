"""
E2E suite: patient manages extended profile and reads empty vaccinations list.
"""

import os

from tests.conftest import AUTH_URL, PATIENT_URL
from tests.helpers.auth import register_patient

CLINICAL_URL = os.getenv("CLINICAL_URL", "http://localhost:8000/clinical")


class TestPatientProfileExtensionsE2E:
    async def test_patient_updates_extended_profile_and_reads_it_back(self, http):
        patient = await register_patient(http, AUTH_URL)
        headers = {"Authorization": f"Bearer {patient['access_token']}"}

        patch_resp = await http.patch(
            f"{PATIENT_URL}/profile",
            headers=headers,
            json={
                "full_name": "E2E Patient",
                "profile_photo_url": "/uploads/profile-photos/manual.png",
                "vital_signs": {
                    "height_cm": 168.0,
                    "weight_kg": 55.0,
                    "blood_pressure": "110/70",
                    "heart_rate_bpm": 69,
                },
                "insurance": {
                    "type": "PRIVATE",
                    "provider": "Bao Viet",
                    "policy_id": "BV-001",
                    "expiry_date": "2030-01-01",
                },
            },
        )
        assert patch_resp.status_code == 200, patch_resp.text

        get_resp = await http.get(f"{PATIENT_URL}/profile", headers=headers)
        assert get_resp.status_code == 200, get_resp.text
        body = get_resp.json()
        assert body["profile"]["full_name"] == "E2E Patient"
        assert body["profile"]["profile_photo_url"]
        assert body["profile"]["insurance"]["type"] == "PRIVATE"

        vaccinations_resp = await http.get(
            f"{CLINICAL_URL}/patients/{patient['user_id']}/vaccinations",
            headers=headers,
        )
        assert vaccinations_resp.status_code == 200, vaccinations_resp.text
        assert isinstance(vaccinations_resp.json(), list)