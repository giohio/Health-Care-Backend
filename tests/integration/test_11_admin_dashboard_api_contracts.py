"""
Integration tests: admin dashboard APIs.

Scope:
- Auth admin config endpoints
- Auth admin users listing and status patch
- Appointment admin stats/chart-data endpoints
- RBAC checks (admin allowed, patient forbidden)
"""

from tests.conftest import APPOINTMENT_URL, AUTH_URL, short_id
from tests.helpers.auth import register_patient


class TestAdminAuthEndpoints:

    async def test_admin_can_get_and_update_config(self, http, admin_token):
        headers = {"Authorization": f"Bearer {admin_token}"}

        get_resp = await http.get(f"{AUTH_URL}/admin/config", headers=headers)
        assert get_resp.status_code == 200, get_resp.text
        get_body = get_resp.json()
        assert get_body["status"] == "success"
        assert "clinic_name" in get_body["data"]

        patch_name = f"HealthAI Admin {short_id()}"
        put_resp = await http.put(
            f"{AUTH_URL}/admin/config",
            headers=headers,
            json={
                "clinic_name": patch_name,
                "maintenance_mode": False,
                "default_slot_duration_minutes": 30,
                "max_appointments_per_day": 80,
                "working_hours_start": "08:00",
                "working_hours_end": "17:00",
            },
        )
        assert put_resp.status_code == 200, put_resp.text
        put_body = put_resp.json()
        assert put_body["status"] == "success"
        assert put_body["data"]["clinic_name"] == patch_name

    async def test_admin_can_list_users_and_toggle_user_status(self, http, admin_token):
        patient = await register_patient(http, AUTH_URL)
        headers = {"Authorization": f"Bearer {admin_token}"}

        list_resp = await http.get(
            f"{AUTH_URL}/admin/users",
            params={"search": patient["email"], "page": 1, "limit": 20},
            headers=headers,
        )
        assert list_resp.status_code == 200, list_resp.text
        body = list_resp.json()
        assert body["status"] == "success"
        users = body["data"]["users"]
        matched = [u for u in users if u["email"] == patient["email"]]
        assert matched, f"Expected to find user {patient['email']} in admin users list"

        deactivate = await http.patch(
            f"{AUTH_URL}/admin/users/{patient['user_id']}/status",
            json={"is_active": False},
            headers=headers,
        )
        assert deactivate.status_code == 200, deactivate.text
        assert deactivate.json()["data"]["is_active"] is False

        login_after_deactivate = await http.post(
            f"{AUTH_URL}/login",
            json={"email": patient["email"], "password": patient["password"]},
        )
        assert login_after_deactivate.status_code == 401

        reactivate = await http.patch(
            f"{AUTH_URL}/admin/users/{patient['user_id']}/status",
            json={"is_active": True},
            headers=headers,
        )
        assert reactivate.status_code == 200, reactivate.text
        assert reactivate.json()["data"]["is_active"] is True

    async def test_patient_forbidden_on_auth_admin_endpoints(self, http):
        patient = await register_patient(http, AUTH_URL)
        headers = {"Authorization": f"Bearer {patient['access_token']}"}

        cfg = await http.get(f"{AUTH_URL}/admin/config", headers=headers)
        assert cfg.status_code == 403

        users = await http.get(f"{AUTH_URL}/admin/users", headers=headers)
        assert users.status_code == 403


class TestAdminAppointmentEndpoints:

    async def test_admin_can_get_stats_and_chart_data(self, http, admin_token):
        headers = {"Authorization": f"Bearer {admin_token}"}

        stats = await http.get(
            f"{APPOINTMENT_URL}/admin/stats",
            params={"range": "month"},
            headers=headers,
        )
        assert stats.status_code == 200, stats.text
        stats_body = stats.json()
        assert stats_body["status"] == "success"
        assert "total_appointments" in stats_body["data"]
        assert "by_status" in stats_body["data"]

        chart = await http.get(
            f"{APPOINTMENT_URL}/admin/chart-data",
            params={"range": "month", "metric": "appointments"},
            headers=headers,
        )
        assert chart.status_code == 200, chart.text
        chart_body = chart.json()
        assert chart_body["status"] == "success"
        assert chart_body["data"]["metric"] == "appointments"
        assert isinstance(chart_body["data"]["data_points"], list)
        assert "peak_day" in chart_body["data"]

    async def test_patient_forbidden_on_appointment_admin_endpoints(self, http):
        patient = await register_patient(http, AUTH_URL)
        headers = {"Authorization": f"Bearer {patient['access_token']}"}

        stats = await http.get(f"{APPOINTMENT_URL}/admin/stats", headers=headers)
        assert stats.status_code == 403

        chart = await http.get(f"{APPOINTMENT_URL}/admin/chart-data", headers=headers)
        assert chart.status_code == 403
