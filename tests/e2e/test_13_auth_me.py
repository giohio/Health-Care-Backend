"""
Test suite: GET /auth/me endpoint.

Covers:
  - Returns current user info (id, email, role, is_active, created_at) from X-User-Id
  - Unauthenticated request returns 401
  - Doctor role reflected correctly
"""

from tests.conftest import AUTH_URL
from tests.helpers.auth import register_doctor, register_patient


class TestAuthMe:

    async def test_me_returns_current_user(self, http):
        """
        GIVEN a registered and logged-in patient
        WHEN GET /auth/me with valid token
        THEN returns {id, email, role='patient', is_active=True, created_at}
        """
        creds = await register_patient(http, AUTH_URL)
        headers = {"Authorization": f"Bearer {creds['access_token']}"}

        r = await http.get(f"{AUTH_URL}/me", headers=headers)
        assert r.status_code == 200
        body = r.json()
        assert body["id"] == creds["user_id"]
        assert body["email"] == creds["email"]
        assert body["role"].lower() == "patient"
        assert body["is_active"] is True
        assert "created_at" in body

    async def test_me_unauthenticated_rejected(self, http):
        """
        GIVEN no Authorization header
        WHEN GET /auth/me is called
        THEN 401 is returned
        """
        http.cookies.clear()
        r = await http.get(f"{AUTH_URL}/me")
        assert r.status_code == 401

    async def test_me_returns_doctor_role(self, http, admin_token, specialty_id):
        """
        GIVEN a registered doctor
        WHEN GET /auth/me with doctor token
        THEN returns role='doctor'
        """
        from tests.conftest import DOCTOR_URL

        doctor = await register_doctor(http, AUTH_URL, DOCTOR_URL, admin_token, specialty_id)
        headers = {"Authorization": f"Bearer {doctor['access_token']}"}

        r = await http.get(f"{AUTH_URL}/me", headers=headers)
        assert r.status_code == 200
        body = r.json()
        assert body["role"].lower() == "doctor"
        assert body["is_active"] is True

    async def test_me_invalid_token_rejected(self, http):
        """
        GIVEN an invalid/expired JWT token
        WHEN GET /auth/me is called
        THEN 401 or 403 is returned
        """
        http.cookies.clear()
        headers = {"Authorization": "Bearer this.is.not.a.valid.token"}
        r = await http.get(f"{AUTH_URL}/me", headers=headers)
        assert r.status_code in (401, 403)
