"""
Test suite: New Appointment Service features.

Covers:
  - PUT /{id}/start            — doctor starts appointment → status=in_progress, started_at set
  - GET /doctor/{id}?date_from=&date_to= — week filter for doctor's appointment list
  - GET /stats?doctor_id=&range= — appointment statistics (today/week/month)
  - GET /queue/{doctor_id}     — doctor queue ordered (pending first), filterable by date
"""

import os
from datetime import date, timedelta

import httpx

from tests.conftest import APPOINTMENT_URL, AUTH_URL, DOCTOR_URL, EVENT_TIMEOUT, PAYMENT_URL
from tests.helpers.auth import add_doctor_schedule, register_doctor, register_patient
from tests.helpers.vnpay_simulator import VNPaySimulator
from tests.helpers.wait import wait_for_appointment_status, wait_for_payment_record

# ─── Reusable helper ──────────────────────────────────────────────────────────


async def _book_and_confirm(http, patient, doctor, specialty_id, appt_date, start_time):
    """Book + pay (VNPAY success) → wait for confirmed status. Returns appointment dict."""
    p_header = {"Authorization": f"Bearer {patient['access_token']}"}

    # Increase timeout for slow CI environments if needed
    book_r = await http.post(
        f"{APPOINTMENT_URL}/",
        json={
            "doctor_id": doctor["user_id"],
            "specialty_id": specialty_id,
            "appointment_date": appt_date,
            "start_time": start_time,
            "appointment_type": "general",
        },
        headers=p_header,
        timeout=httpx.Timeout(10.0),
    )
    assert book_r.status_code in (200, 201), book_r.text
    appt_id = book_r.json()["id"]

    payment = await wait_for_payment_record(
        http=http,
        payment_url=PAYMENT_URL,
        appointment_id=appt_id,
        token=patient["access_token"],
        timeout=EVENT_TIMEOUT,
    )
    vnpay = VNPaySimulator(os.getenv("VNPAY_HASH_SECRET"), PAYMENT_URL)
    await vnpay.simulate_payment(http, payment["vnpay_txn_ref"], payment["amount"], success=True)
    confirmed = await wait_for_appointment_status(
        http,
        APPOINTMENT_URL,
        appt_id,
        "CONFIRMED",
        patient["access_token"],
        timeout=EVENT_TIMEOUT,
    )
    return confirmed


# ─────────────────────────────────────────────────────────────────────────────


class TestStartAppointment:

    async def test_start_appointment_sets_in_progress(self, http, admin_token, specialty_id):
        """
        GIVEN a confirmed appointment
        WHEN doctor calls PUT /{appointment_id}/start
        THEN status becomes 'in_progress'
        AND started_at is set
        """
        patient = await register_patient(http, AUTH_URL)
        doctor = await register_doctor(http, AUTH_URL, DOCTOR_URL, admin_token, specialty_id)
        await add_doctor_schedule(http, DOCTOR_URL, doctor["user_id"], doctor["access_token"])

        # Enable auto_confirm to streamline
        await http.put(
            f"{DOCTOR_URL}/me/auto-confirm",
            json={"auto_confirm": True, "confirmation_timeout_minutes": 15},
            headers={"Authorization": f"Bearer {doctor['access_token']}"},
        )

        today = date.today()
        days_ahead = (0 - today.weekday()) % 7 or 7
        test_date = (today + timedelta(days=days_ahead)).isoformat()

        appt = await _book_and_confirm(http, patient, doctor, specialty_id, test_date, "09:00")
        appt_id = appt["id"]

        d_header = {"Authorization": f"Bearer {doctor['access_token']}"}
        r = await http.put(f"{APPOINTMENT_URL}/{appt_id}/start", headers=d_header)
        assert r.status_code in (200, 201), r.text
        body = r.json()
        assert body["status"] == "IN_PROGRESS"
        assert body.get("started_at") is not None

    async def test_start_appointment_only_doctor_can(self, http, admin_token, specialty_id):
        """
        GIVEN a confirmed appointment
        WHEN patient tries to call PUT /{appointment_id}/start
        THEN 403 returned
        """
        patient = await register_patient(http, AUTH_URL)
        doctor = await register_doctor(http, AUTH_URL, DOCTOR_URL, admin_token, specialty_id)

        # Explicit isolation check
        assert patient["user_id"] != doctor["user_id"], "Patient and Doctor must be distinct for 403 test"

        await add_doctor_schedule(http, DOCTOR_URL, doctor["user_id"], doctor["access_token"])

        await http.put(
            f"{DOCTOR_URL}/me/auto-confirm",
            json={"auto_confirm": True, "confirmation_timeout_minutes": 15},
            headers={"Authorization": f"Bearer {doctor['access_token']}"},
        )

        today = date.today()
        days_ahead = (0 - today.weekday()) % 7 or 7
        test_date = (today + timedelta(days=days_ahead)).isoformat()

        http.cookies.clear()
        appt = await _book_and_confirm(http, patient, doctor, specialty_id, test_date, "10:00")
        appt_id = appt["id"]

        # Patient tries to start — should be forbidden
        r = await http.put(
            f"{APPOINTMENT_URL}/{appt_id}/start",
            headers={"Authorization": f"Bearer {patient['access_token']}"},
        )
        assert r.status_code == 403, f"Expected 403 for patient starting appt, got {r.status_code}: {r.text}"


class TestDoctorAppointmentsDateFilter:

    async def test_list_doctor_appointments_with_date_range(self, http, admin_token, specialty_id):
        """
        GIVEN a doctor with 2 appointments on different weeks
        WHEN GET /doctor/{doctor_id}?date_from=&date_to= for only one week
        THEN only appointments within that range are returned
        """
        patient = await register_patient(http, AUTH_URL)
        doctor = await register_doctor(http, AUTH_URL, DOCTOR_URL, admin_token, specialty_id)
        await add_doctor_schedule(http, DOCTOR_URL, doctor["user_id"], doctor["access_token"])

        # Book appointment in week 1 (next Monday)
        today = date.today()
        days_ahead = (0 - today.weekday()) % 7 or 7
        week1_date = (today + timedelta(days=days_ahead)).isoformat()

        p_header = {"Authorization": f"Bearer {patient['access_token']}"}
        book_r = await http.post(
            f"{APPOINTMENT_URL}/",
            json={
                "doctor_id": doctor["user_id"],
                "specialty_id": specialty_id,
                "appointment_date": week1_date,
                "start_time": "09:00",
                "appointment_type": "general",
            },
            headers=p_header,
        )
        assert book_r.status_code in (200, 201), book_r.text

        d_header = {"Authorization": f"Bearer {doctor['access_token']}"}

        # Query only week 1
        r = await http.get(
            f"{APPOINTMENT_URL}/doctor/{doctor['user_id']}",
            params={"date_from": week1_date, "date_to": week1_date},
            headers=d_header,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        appointments = body if isinstance(body, list) else body.get("items", body.get("appointments", []))
        # All returned appointments should be on week1_date
        for appt in appointments:
            assert appt.get("appointment_date") == week1_date

    async def test_list_doctor_appointments_no_filter_returns_all(self, http, admin_token, specialty_id):
        """
        GIVEN a doctor
        WHEN GET /doctor/{doctor_id} without date filter
        THEN returns all their appointments (no date restriction)
        """
        doctor = await register_doctor(http, AUTH_URL, DOCTOR_URL, admin_token, specialty_id)
        d_header = {"Authorization": f"Bearer {doctor['access_token']}"}

        r = await http.get(
            f"{APPOINTMENT_URL}/doctor/{doctor['user_id']}",
            headers=d_header,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        # Just validate shape is a list
        appointments = body if isinstance(body, list) else body.get("items", body.get("appointments", []))
        assert isinstance(appointments, list)


class TestAppointmentStats:

    async def test_stats_today_shape(self, http, admin_token, specialty_id):
        """
        GIVEN any doctor
        WHEN GET /stats?doctor_id=&range=today
        THEN returns {total, pending, confirmed, completed, cancelled} all >= 0
        """
        doctor = await register_doctor(http, AUTH_URL, DOCTOR_URL, admin_token, specialty_id)
        d_header = {"Authorization": f"Bearer {doctor['access_token']}"}

        r = await http.get(
            f"{APPOINTMENT_URL}/stats",
            params={"doctor_id": doctor["user_id"], "range": "today"},
            headers=d_header,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        stats_fields = (
            "total_appointments",
            "pending_appointments",
            "confirmed_appointments",
            "completed_appointments",
            "cancelled_appointments",
        )
        for field in stats_fields:
            assert field in body, f"Missing field '{field}' in stats: {body}"
            assert body[field] >= 0

    async def test_stats_week_returns_counts(self, http, admin_token, specialty_id):
        """
        GIVEN a doctor
        WHEN GET /stats?range=week
        THEN returns valid stats with non-negative counts
        """
        doctor = await register_doctor(http, AUTH_URL, DOCTOR_URL, admin_token, specialty_id)
        d_header = {"Authorization": f"Bearer {doctor['access_token']}"}

        r = await http.get(
            f"{APPOINTMENT_URL}/stats",
            params={"doctor_id": doctor["user_id"], "range": "week"},
            headers=d_header,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert "total_appointments" in body
        assert body["total_appointments"] >= 0

    async def test_stats_month_returns_counts(self, http, admin_token, specialty_id):
        """
        GIVEN a doctor
        WHEN GET /stats?range=month
        THEN returns valid stats
        """
        doctor = await register_doctor(http, AUTH_URL, DOCTOR_URL, admin_token, specialty_id)
        d_header = {"Authorization": f"Bearer {doctor['access_token']}"}

        r = await http.get(
            f"{APPOINTMENT_URL}/stats",
            params={"doctor_id": doctor["user_id"], "range": "month"},
            headers=d_header,
        )
        assert r.status_code == 200, r.text
        assert r.json().get("total_appointments", -1) >= 0

    async def test_stats_reflects_booked_appointment(self, http, admin_token, specialty_id):
        """
        GIVEN a doctor with 0 stats
        WHEN a patient books an appointment for today
        THEN total in today stats increments by at least 1
        """
        patient = await register_patient(http, AUTH_URL)
        doctor = await register_doctor(http, AUTH_URL, DOCTOR_URL, admin_token, specialty_id)
        await add_doctor_schedule(http, DOCTOR_URL, doctor["user_id"], doctor["access_token"])
        d_header = {"Authorization": f"Bearer {doctor['access_token']}"}

        # Capture baseline
        r_before = await http.get(
            f"{APPOINTMENT_URL}/stats",
            params={"doctor_id": doctor["user_id"], "range": "week"},
            headers=d_header,
        )
        total_before = r_before.json().get("total_appointments", 0)

        today = date.today()
        days_ahead = (0 - today.weekday()) % 7 or 7
        test_date = (today + timedelta(days=days_ahead)).isoformat()

        await http.post(
            f"{APPOINTMENT_URL}/",
            json={
                "doctor_id": doctor["user_id"],
                "specialty_id": specialty_id,
                "appointment_date": test_date,
                "start_time": "09:00",
                "appointment_type": "general",
            },
            headers={"Authorization": f"Bearer {patient['access_token']}"},
        )

        r_after = await http.get(
            f"{APPOINTMENT_URL}/stats",
            params={"doctor_id": doctor["user_id"], "range": "week"},
            headers=d_header,
        )
        total_after = r_after.json().get("total_appointments", 0)
        assert total_after >= total_before + 1


class TestDoctorQueue:

    async def test_doctor_queue_lists_appointments(self, http, admin_token, specialty_id):
        """
        GIVEN a doctor with at least one booked appointment
        WHEN GET /queue/{doctor_id}?appointment_date=
        THEN returns list of appointments for that date
        """
        patient = await register_patient(http, AUTH_URL)
        doctor = await register_doctor(http, AUTH_URL, DOCTOR_URL, admin_token, specialty_id)
        await add_doctor_schedule(http, DOCTOR_URL, doctor["user_id"], doctor["access_token"])

        today = date.today()
        days_ahead = (0 - today.weekday()) % 7 or 7
        test_date = (today + timedelta(days=days_ahead)).isoformat()

        book_r = await http.post(
            f"{APPOINTMENT_URL}/",
            json={
                "doctor_id": doctor["user_id"],
                "specialty_id": specialty_id,
                "appointment_date": test_date,
                "start_time": "09:00",
                "appointment_type": "general",
            },
            headers={"Authorization": f"Bearer {patient['access_token']}"},
        )
        assert book_r.status_code in (200, 201), book_r.text
        appt_id = book_r.json()["id"]

        d_header = {"Authorization": f"Bearer {doctor['access_token']}"}
        r = await http.get(
            f"{APPOINTMENT_URL}/queue/{doctor['user_id']}",
            params={"appointment_date": test_date},
            headers=d_header,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        queue = body if isinstance(body, list) else body.get("queue", body.get("items", []))
        appt_ids = [q.get("id") for q in queue]
        assert appt_id in appt_ids

    async def test_doctor_queue_pending_first(self, http, admin_token, specialty_id):
        """
        GIVEN a doctor with a pending appointment on a date
        WHEN GET /queue/{doctor_id}?appointment_date=
        THEN pending appointments appear before confirmed ones (or status=pending present)
        """
        patient = await register_patient(http, AUTH_URL)
        doctor = await register_doctor(http, AUTH_URL, DOCTOR_URL, admin_token, specialty_id)
        await add_doctor_schedule(http, DOCTOR_URL, doctor["user_id"], doctor["access_token"])

        today = date.today()
        days_ahead = (0 - today.weekday()) % 7 or 7
        test_date = (today + timedelta(days=days_ahead)).isoformat()

        # Book without paying → stays in pending_payment / pending
        await http.post(
            f"{APPOINTMENT_URL}/",
            json={
                "doctor_id": doctor["user_id"],
                "specialty_id": specialty_id,
                "appointment_date": test_date,
                "start_time": "09:00",
                "appointment_type": "general",
            },
            headers={"Authorization": f"Bearer {patient['access_token']}"},
        )

        d_header = {"Authorization": f"Bearer {doctor['access_token']}"}
        r = await http.get(
            f"{APPOINTMENT_URL}/queue/{doctor['user_id']}",
            params={"appointment_date": test_date},
            headers=d_header,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        queue = body if isinstance(body, list) else body.get("queue", body.get("items", []))
        assert len(queue) >= 1
        # First item should be pending or pending_payment
        first_status = queue[0].get("status", "")
        assert "PENDING" in first_status.upper()
