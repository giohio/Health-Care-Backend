"""
E2E suite: Admin dashboard APIs across auth + appointment services.

Flow coverage:
- Admin updates and reads system configuration
- Admin lists users and toggles patient active status
- Admin views appointment stats/chart after a real booking action
"""

from datetime import date

from tests.conftest import APPOINTMENT_URL, AUTH_URL, DOCTOR_URL
from tests.helpers.auth import add_doctor_schedule, register_doctor, register_patient


class TestAdminDashboardAPIs:

    async def test_admin_config_and_user_management_flow(self, http, admin_token):
        admin_headers = {"Authorization": f"Bearer {admin_token}"}

        patient = await register_patient(http, AUTH_URL)

        update_cfg = await http.put(
            f"{AUTH_URL}/admin/config",
            headers=admin_headers,
            json={
                "clinic_name": "HealthAI Dashboard Clinic",
                "maintenance_mode": False,
                "default_slot_duration_minutes": 30,
                "max_appointments_per_day": 60,
                "working_hours_start": "08:00",
                "working_hours_end": "17:00",
            },
        )
        assert update_cfg.status_code == 200, update_cfg.text
        assert update_cfg.json()["status"] == "success"

        read_cfg = await http.get(f"{AUTH_URL}/admin/config", headers=admin_headers)
        assert read_cfg.status_code == 200, read_cfg.text
        cfg_body = read_cfg.json()
        assert cfg_body["status"] == "success"
        assert cfg_body["data"]["default_slot_duration_minutes"] in (15, 30, 45, 60)

        users = await http.get(
            f"{AUTH_URL}/admin/users",
            params={"search": patient["email"], "page": 1, "limit": 20},
            headers=admin_headers,
        )
        assert users.status_code == 200, users.text
        users_body = users.json()
        assert users_body["status"] == "success"
        assert any(u["email"] == patient["email"] for u in users_body["data"]["users"])

        deactivate = await http.patch(
            f"{AUTH_URL}/admin/users/{patient['user_id']}/status",
            headers=admin_headers,
            json={"is_active": False},
        )
        assert deactivate.status_code == 200, deactivate.text
        assert deactivate.json()["data"]["is_active"] is False

        blocked_login = await http.post(
            f"{AUTH_URL}/login",
            json={"email": patient["email"], "password": patient["password"]},
        )
        assert blocked_login.status_code == 401

        reactivate = await http.patch(
            f"{AUTH_URL}/admin/users/{patient['user_id']}/status",
            headers=admin_headers,
            json={"is_active": True},
        )
        assert reactivate.status_code == 200, reactivate.text
        assert reactivate.json()["data"]["is_active"] is True

    async def test_admin_stats_and_chart_reflect_real_booking(self, http, admin_token, specialty_id):
        admin_headers = {"Authorization": f"Bearer {admin_token}"}

        patient = await register_patient(http, AUTH_URL)
        doctor = await register_doctor(http, AUTH_URL, DOCTOR_URL, admin_token, specialty_id)
        await add_doctor_schedule(http, DOCTOR_URL, doctor["user_id"], doctor["access_token"])

        # Ensure the doctor is available every day so booking can be created for today.
        schedule_all_days = await http.put(
            f"{DOCTOR_URL}/{doctor['user_id']}/schedule",
            json=[
                {
                    "doctor_id": doctor["user_id"],
                    "day_of_week": day,
                    "start_time": "08:00",
                    "end_time": "17:00",
                    "slot_duration_minutes": 20,
                }
                for day in range(7)
            ],
            headers={"Authorization": f"Bearer {doctor['access_token']}"},
        )
        assert schedule_all_days.status_code == 200, schedule_all_days.text

        # Book one appointment so dashboard stats have real data.
        appt_date = date.today().isoformat()

        booking = await http.post(
            f"{APPOINTMENT_URL}/",
            json={
                "doctor_id": doctor["user_id"],
                "specialty_id": specialty_id,
                "appointment_date": appt_date,
                "start_time": "09:00",
                "appointment_type": "general",
            },
            headers={"Authorization": f"Bearer {patient['access_token']}"},
        )
        assert booking.status_code in (200, 201), booking.text

        stats = await http.get(
            f"{APPOINTMENT_URL}/admin/stats",
            params={"range": "month"},
            headers=admin_headers,
        )
        assert stats.status_code == 200, stats.text
        stats_body = stats.json()
        assert stats_body["status"] == "success"
        assert stats_body["data"]["total_appointments"] >= 1
        assert "by_status" in stats_body["data"]

        chart = await http.get(
            f"{APPOINTMENT_URL}/admin/chart-data",
            params={"range": "month", "metric": "appointments"},
            headers=admin_headers,
        )
        assert chart.status_code == 200, chart.text
        chart_body = chart.json()
        assert chart_body["status"] == "success"
        assert chart_body["data"]["metric"] == "appointments"
        assert chart_body["data"]["total"] >= 1
        assert any(point["value"] > 0 for point in chart_body["data"]["data_points"])
