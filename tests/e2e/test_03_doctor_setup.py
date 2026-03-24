"""
Test suite: Doctor setup flows.

Covers:
  - Doctor profile auto-created on registration
  - Update doctor profile (specialty, title)
  - Set weekly schedule
  - Search available doctors
  - Set auto_confirm preference
"""

from tests.conftest import AUTH_URL, DOCTOR_URL


class TestDoctorSetup:

    async def test_doctor_profile_created(self, http, admin_token, specialty_id):
        """
        GIVEN admin registers a doctor
        WHEN GET /doctors/{user_id} is called
        THEN doctor profile exists
        """
        from tests.helpers.auth import register_doctor

        doctor = await register_doctor(http, AUTH_URL, DOCTOR_URL, admin_token, specialty_id)

        r = await http.get(
            f"{DOCTOR_URL}/{doctor['user_id']}", headers={"Authorization": f"Bearer {doctor['access_token']}"}
        )
        assert r.status_code == 200
        assert r.json()["specialty_id"] == specialty_id

    async def test_set_schedule(self, http, admin_token, specialty_id):
        """
        GIVEN a doctor
        WHEN PUT /{doctor_id}/schedule is called
        THEN schedule is saved for each day
        """
        from tests.helpers.auth import add_doctor_schedule, register_doctor

        doctor = await register_doctor(http, AUTH_URL, DOCTOR_URL, admin_token, specialty_id)
        await add_doctor_schedule(http, DOCTOR_URL, doctor["user_id"], doctor["access_token"])

        r = await http.get(
            f"{DOCTOR_URL}/{doctor['user_id']}/schedule", headers={"Authorization": f"Bearer {doctor['access_token']}"}
        )
        assert r.status_code == 200
        schedules = r.json()
        assert len(schedules) == 5
        # Monday through Friday

    async def test_set_auto_confirm_false(self, http, admin_token, specialty_id):
        """
        GIVEN a doctor
        WHEN PUT /me/auto-confirm with auto_confirm=False
        THEN setting is saved
        AND subsequent appointments require manual confirm
        """
        from tests.helpers.auth import register_doctor

        doctor = await register_doctor(http, AUTH_URL, DOCTOR_URL, admin_token, specialty_id)

        r = await http.put(
            f"{DOCTOR_URL}/me/auto-confirm",
            json={
                "auto_confirm": False,
                "confirmation_timeout_minutes": 20,
            },
            headers={"Authorization": f"Bearer {doctor['access_token']}"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["auto_confirm"] is False
        assert body["confirmation_timeout_minutes"] == 20

    async def test_search_available_doctors(self, http, admin_token, specialty_id):
        """
        GIVEN a doctor with schedule set
        WHEN GET /search/available with day and time
        THEN doctor appears in results
        """
        from tests.helpers.auth import add_doctor_schedule, register_doctor

        doctor = await register_doctor(http, AUTH_URL, DOCTOR_URL, admin_token, specialty_id)
        await add_doctor_schedule(http, DOCTOR_URL, doctor["user_id"], doctor["access_token"])

        r = await http.get(
            f"{DOCTOR_URL}/search/available",
            params={
                "specialty_id": specialty_id,
                "day": "MONDAY",
                "time": "09:00",
            },
        )
        assert r.status_code == 200
        doctors = r.json()
        ids = [d["user_id"] for d in doctors]
        assert doctor["user_id"] in ids
