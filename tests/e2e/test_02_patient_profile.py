"""
Test suite: Patient profile flows.

Covers:
  - Profile auto-created on registration
  - GET profile returns blank profile
  - Update profile (mandatory fields)
  - is_profile_completed propagates to Auth
  - Update health background
  - Internal full-context endpoint
"""

from tests.conftest import AUTH_URL, EVENT_TIMEOUT, PATIENT_URL, short_id
from tests.helpers.auth import register_patient
from tests.helpers.wait import poll_until


class TestPatientProfile:

    async def test_profile_auto_created(self, http):
        """
        GIVEN a newly registered patient
        WHEN GET /patients/ is called
        THEN a blank profile is returned
        (auto-created via user.registered event)
        """
        creds = await register_patient(http, AUTH_URL)

        # Wait for user.registered event processing
        async def fetch():
            r = await http.get(f"{PATIENT_URL}/", headers={"Authorization": f"Bearer {creds['access_token']}"})
            return r

        resp = await poll_until(
            fn=fetch, check=lambda r: r.status_code == 200, timeout=EVENT_TIMEOUT, label="patient profile auto-created"
        )
        body = resp.json()
        assert "profile" in body

    async def test_update_profile_sets_completed(self, http):
        """
        GIVEN a patient with blank profile
        WHEN PUT /profile with full_name, dob, gender
        THEN profile is updated
        AND is_profile_completed becomes True in Auth
        (propagated via profile.completed event)
        """
        creds = await register_patient(http, AUTH_URL)
        headers = {"Authorization": f"Bearer {creds['access_token']}"}

        # Update profile with all mandatory fields
        r = await http.put(
            f"{PATIENT_URL}/profile",
            json={
                "full_name": f"Test Patient {short_id()}",
                "date_of_birth": "1990-01-15",
                "gender": "FEMALE",
                "phone_number": "0901234567",
            },
            headers=headers,
        )
        assert r.status_code == 200

        # Wait for profile.completed event to propagate
        # to Auth Service (is_profile_completed = true)
        latest_refresh_token = creds["refresh_token"]

        async def check_auth():
            nonlocal latest_refresh_token
            # Refresh token to get new claims
            r2 = await http.post(f"{AUTH_URL}/refresh", json={"refresh_token": latest_refresh_token})
            if r2.status_code == 200:
                body = r2.json()
                latest_refresh_token = body.get("refresh_token", latest_refresh_token)
                return body
            return r2.json()

        result = await poll_until(
            fn=check_auth,
            check=lambda r: r.get("user", {}).get("is_profile_completed") is True,
            timeout=EVENT_TIMEOUT,
            label="is_profile_completed=True",
        )
        assert result["user"]["is_profile_completed"] is True

        # Immediate read-after-write should reflect the new value (cache invalidation correctness)
        latest_profile = await http.get(f"{PATIENT_URL}/", headers=headers)
        assert latest_profile.status_code == 200
        assert latest_profile.json()["profile"]["full_name"].startswith("Test Patient")

    async def test_update_health_background(self, http):
        """
        GIVEN a patient
        WHEN PUT /health with blood_type, allergies
        THEN health background is saved
        """
        creds = await register_patient(http, AUTH_URL)
        headers = {"Authorization": f"Bearer {creds['access_token']}"}

        r = await http.put(
            f"{PATIENT_URL}/health",
            json={
                "blood_type": "A",
                "height_cm": 165,
                "weight_kg": 55.0,
                "allergies": ["Penicillin"],
                "chronic_conditions": ["Diabetes"],
            },
            headers=headers,
        )
        assert r.status_code == 200
        body = r.json()
        assert body["blood_type"] == "A"
        assert "Penicillin" in body["allergies"]

    async def test_internal_full_context(self, http):
        """
        GIVEN a patient with profile and health data
        WHEN GET /internal/patients/{id}/full-context
        THEN both profile and health_background returned
        """
        creds = await register_patient(http, AUTH_URL)
        await http.put(
            f"{PATIENT_URL}/health",
            json={"blood_type": "B", "allergies": ["Aspirin"]},
            headers={"Authorization": f"Bearer {creds['access_token']}"},
        )

        r = await http.get(f"{PATIENT_URL}/internal/patients/{creds['user_id']}/full-context")
        assert r.status_code == 200
        body = r.json()
        assert "profile" in body
        assert "health_background" in body
        assert "Aspirin" in (body["health_background"].get("allergies", []))
