"""
Integration: auth and RBAC behavior across services.
"""

from tests.conftest import AUTH_URL, DOCTOR_URL, PAYMENT_URL
from tests.helpers.auth import register_doctor, register_patient


class TestAuthRbacCrossService:
    async def test_payments_my_requires_auth_and_works_with_patient_token(self, http):
        unauth = await http.get(f"{PAYMENT_URL}/my")
        assert unauth.status_code == 401

        patient = await register_patient(http, AUTH_URL)
        auth = await http.get(
            f"{PAYMENT_URL}/my",
            headers={"Authorization": f"Bearer {patient['access_token']}"},
        )
        assert auth.status_code == 200, auth.text
        assert isinstance(auth.json(), list)

    async def test_patient_forbidden_on_doctor_only_operation(self, http):
        patient = await register_patient(http, AUTH_URL)
        resp = await http.put(
            f"{DOCTOR_URL}/me/auto-confirm",
            json={"auto_confirm": False, "confirmation_timeout_minutes": 15},
            headers={"Authorization": f"Bearer {patient['access_token']}"},
        )
        assert resp.status_code == 403

    async def test_doctor_can_update_auto_confirm_policy(self, http, admin_token, specialty_id):
        doctor = await register_doctor(http, AUTH_URL, DOCTOR_URL, admin_token, specialty_id)
        resp = await http.put(
            f"{DOCTOR_URL}/me/auto-confirm",
            json={"auto_confirm": False, "confirmation_timeout_minutes": 20},
            headers={"Authorization": f"Bearer {doctor['access_token']}"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body.get("auto_confirm") is False
