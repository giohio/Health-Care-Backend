"""
Test suite: Patient Vitals & Health Summary.

Covers:
  - POST /{patient_id}/vitals — records vitals
  - GET /{patient_id}/vitals/latest — returns most recent
  - GET /{patient_id}/vitals — paginated history
  - GET /health-summary — aggregated profile + health background
  - Authorization: only the patient themselves can record/view their vitals
"""

from tests.conftest import AUTH_URL, PATIENT_URL
from tests.helpers.auth import register_patient


class TestPatientVitals:

    async def test_record_vitals_success(self, http):
        """
        GIVEN a registered patient
        WHEN POST /{patient_id}/vitals with all fields
        THEN 200 or 201 returned
        AND body includes the recorded fields
        """
        creds = await register_patient(http, AUTH_URL)
        headers = {"Authorization": f"Bearer {creds['access_token']}"}

        r = await http.post(
            f"{PATIENT_URL}/{creds['user_id']}/vitals",
            params={
                "height_cm": 175.5,
                "weight_kg": 70.2,
                "blood_pressure_systolic": 120,
                "blood_pressure_diastolic": 80,
                "heart_rate": 72,
                "temperature_celsius": 36.6,
            },
            headers=headers,
        )
        assert r.status_code in (200, 201), r.text
        body = r.json()
        assert abs(body["height_cm"] - 175.5) < 0.001
        assert abs(body["weight_kg"] - 70.2) < 0.001
        assert body["heart_rate"] == 72

    async def test_get_latest_vitals(self, http):
        """
        GIVEN a patient who has recorded vitals
        WHEN GET /{patient_id}/vitals/latest
        THEN returns the most recently recorded vitals
        """
        creds = await register_patient(http, AUTH_URL)
        headers = {"Authorization": f"Bearer {creds['access_token']}"}

        # Record first entry
        await http.post(
            f"{PATIENT_URL}/{creds['user_id']}/vitals",
            params={"height_cm": 165.0, "weight_kg": 60.0, "heart_rate": 70},
            headers=headers,
        )
        # Record second (latest)
        await http.post(
            f"{PATIENT_URL}/{creds['user_id']}/vitals",
            params={"height_cm": 165.0, "weight_kg": 61.0, "heart_rate": 75},
            headers=headers,
        )

        r = await http.get(
            f"{PATIENT_URL}/{creds['user_id']}/vitals/latest",
            headers=headers,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        # Latest recording should have weight_kg=61.0
        assert abs(body["vitals"]["weight_kg"] - 61.0) < 0.001
        assert body["vitals"]["heart_rate"] == 75

    async def test_get_vitals_history_paginated(self, http):
        """
        GIVEN a patient who has recorded vitals 3 times
        WHEN GET /{patient_id}/vitals
        THEN returns a list with at least 3 records
        """
        creds = await register_patient(http, AUTH_URL)
        headers = {"Authorization": f"Bearer {creds['access_token']}"}

        for i in range(3):
            await http.post(
                f"{PATIENT_URL}/{creds['user_id']}/vitals",
                params={"heart_rate": 70 + i, "weight_kg": 60.0 + i},
                headers=headers,
            )

        r = await http.get(
            f"{PATIENT_URL}/{creds['user_id']}/vitals",
            headers=headers,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        # Could be a list directly or {items: [...], total: N}
        records = body if isinstance(body, list) else body.get("items", body.get("vitals", []))
        assert len(records) >= 3

    async def test_vitals_no_records_returns_empty_or_404(self, http):
        """
        GIVEN a fresh patient with no vitals recorded
        WHEN GET /{patient_id}/vitals/latest
        THEN returns 404 or empty response
        """
        creds = await register_patient(http, AUTH_URL)
        headers = {"Authorization": f"Bearer {creds['access_token']}"}

        r = await http.get(
            f"{PATIENT_URL}/{creds['user_id']}/vitals/latest",
            headers=headers,
        )
        assert r.status_code in (200, 404)
        if r.status_code == 200:
            body = r.json()
            # If 200, body should be null/None or an empty dict
            assert body is None or body == {} or body == []

    async def test_health_summary_returns_aggregated_data(self, http):
        """
        GIVEN a patient with profile and health data
        WHEN GET /health-summary
        THEN returns object containing profile + health background fields
        """
        creds = await register_patient(http, AUTH_URL)
        headers = {"Authorization": f"Bearer {creds['access_token']}"}

        # Update health background first
        await http.put(
            f"{PATIENT_URL}/health",
            json={"blood_type": "O", "allergies": ["Ibuprofen"]},
            headers=headers,
        )

        r = await http.get(f"{PATIENT_URL}/health-summary", headers=headers)
        assert r.status_code == 200, r.text
        body = r.json()
        # Should contain at least a profile reference
        # (exact structure depends on implementation)
        assert body is not None
        assert isinstance(body, dict)
        # Common expected shapes
        has_profile = "profile" in body or "full_name" in body or "user_id" in body
        assert has_profile, f"Health summary missing profile data: {body}"

    async def test_vitals_other_patient_access_rejected(self, http):
        """
        GIVEN two different patients
        WHEN patient2 tries to GET patient1's vitals
        THEN 401, 403, or 404 returned
        """
        patient1 = await register_patient(http, AUTH_URL)
        patient2 = await register_patient(http, AUTH_URL)

        # Record vitals for patient1
        await http.post(
            f"{PATIENT_URL}/{patient1['user_id']}/vitals",
            params={"heart_rate": 70},
            headers={"Authorization": f"Bearer {patient1['access_token']}"},
        )

        # Patient2 tries to access patient1's latest vitals
        r = await http.get(
            f"{PATIENT_URL}/{patient1['user_id']}/vitals/latest",
            headers={"Authorization": f"Bearer {patient2['access_token']}"},
        )
        assert r.status_code in (401, 403, 404)
