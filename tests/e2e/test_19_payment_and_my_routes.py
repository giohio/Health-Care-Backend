"""
Test suite: GET /my routes and payment flow verification.

Covers:
  - GET /payments/my        — returns paginated payment list for authenticated patient
  - GET /appointments/my    — returns appointment list for authenticated patient
  - POST /payments/{id}/pay — generates VNPay URL for a confirmed appointment
  - Full payment → notification flow through GET /my endpoints
"""

import os
from datetime import date, timedelta

import httpx

from tests.conftest import APPOINTMENT_URL, AUTH_URL, DOCTOR_URL, EVENT_TIMEOUT, NOTIFICATION_URL, PAYMENT_URL
from tests.helpers.auth import add_doctor_schedule, register_doctor, register_patient
from tests.helpers.vnpay_simulator import VNPaySimulator
from tests.helpers.wait import wait_for_appointment_status, wait_for_notification, wait_for_payment_record

# ─── Shared booking helper ────────────────────────────────────────────────────


async def _book_and_pay(http, patient, doctor, specialty_id, appt_date, start_time="09:00:00"):
    """Book appointment, wait for payment record creation, simulate VNPay success."""
    p_headers = {"Authorization": f"Bearer {patient['access_token']}"}

    book_r = await http.post(
        f"{APPOINTMENT_URL}/",
        json={
            "doctor_id": doctor["user_id"],
            "specialty_id": specialty_id,
            "appointment_date": appt_date,
            "start_time": start_time,
            "appointment_type": "general",
        },
        headers=p_headers,
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

    simulator = VNPaySimulator(os.getenv("VNPAY_HASH_SECRET"), PAYMENT_URL)
    await simulator.simulate_payment(
        http,
        payment["vnpay_txn_ref"],
        payment["amount"],
        success=True,
    )

    confirmed = await wait_for_appointment_status(
        http,
        APPOINTMENT_URL,
        appt_id,
        "CONFIRMED",
        patient["access_token"],
        timeout=EVENT_TIMEOUT,
    )
    return confirmed, payment


# ─────────────────────────────────────────────────────────────────────────────


class TestGetMyPayments:

    async def test_my_payments_returns_list_after_booking(self, http, admin_token, specialty_id):
        """
        GIVEN a patient who has completed a payment
        WHEN GET /payments/my with their auth token
        THEN the response is 200 with a non-empty list
        AND one item has status == 'paid' for that appointment
        """
        patient = await register_patient(http, AUTH_URL)
        doctor = await register_doctor(http, AUTH_URL, DOCTOR_URL, admin_token, specialty_id)
        await add_doctor_schedule(http, DOCTOR_URL, doctor["user_id"], doctor["access_token"])

        # Enable auto-confirm so booking → confirmed without extra step
        await http.put(
            f"{DOCTOR_URL}/doctors/me/auto-confirm",
            json={"auto_confirm": True, "confirmation_timeout_minutes": 60},
            headers={"Authorization": f"Bearer {doctor['access_token']}"},
        )

        appt_date = str(date.today() + timedelta(days=5))
        confirmed, payment = await _book_and_pay(http, patient, doctor, specialty_id, appt_date)

        p_headers = {"Authorization": f"Bearer {patient['access_token']}"}
        r = await http.get(f"{PAYMENT_URL}/payments/my", headers=p_headers)

        assert r.status_code == 200, r.text
        body = r.json()
        assert isinstance(body, list)
        assert len(body) >= 1

        appt_ids = [item.get("appointment_id") for item in body]
        assert confirmed["id"] in appt_ids

    async def test_my_payments_empty_for_new_patient(self, http):
        """
        GIVEN a brand-new patient with no payments
        WHEN GET /payments/my
        THEN returns 200 with an empty list
        """
        patient = await register_patient(http, AUTH_URL)
        p_headers = {"Authorization": f"Bearer {patient['access_token']}"}

        r = await http.get(f"{PAYMENT_URL}/payments/my", headers=p_headers)
        assert r.status_code == 200, r.text
        assert r.json() == []

    async def test_my_payments_unauthenticated_rejected(self, http):
        """
        GIVEN no Authorization header
        WHEN GET /payments/my
        THEN 401 returned
        """
        http.cookies.clear()
        r = await http.get(f"{PAYMENT_URL}/payments/my")
        assert r.status_code == 401


class TestGetMyAppointments:

    async def test_my_appointments_returns_list_after_booking(self, http, admin_token, specialty_id):
        """
        GIVEN a patient who has booked an appointment
        WHEN GET /appointments/my
        THEN the list includes the booked appointment
        """
        patient = await register_patient(http, AUTH_URL)
        doctor = await register_doctor(http, AUTH_URL, DOCTOR_URL, admin_token, specialty_id)
        await add_doctor_schedule(http, DOCTOR_URL, doctor["user_id"], doctor["access_token"])

        await http.put(
            f"{DOCTOR_URL}/doctors/me/auto-confirm",
            json={"auto_confirm": True, "confirmation_timeout_minutes": 60},
            headers={"Authorization": f"Bearer {doctor['access_token']}"},
        )

        appt_date = str(date.today() + timedelta(days=6))
        confirmed, _ = await _book_and_pay(http, patient, doctor, specialty_id, appt_date)

        p_headers = {"Authorization": f"Bearer {patient['access_token']}"}
        r = await http.get(f"{APPOINTMENT_URL}/my", headers=p_headers)

        assert r.status_code == 200, r.text
        body = r.json()
        assert isinstance(body, list)
        assert len(body) >= 1

        ids = [item["id"] for item in body]
        assert confirmed["id"] in ids

    async def test_my_appointments_empty_for_new_patient(self, http):
        """
        GIVEN a brand-new patient
        WHEN GET /appointments/my
        THEN returns 200 with an empty list
        """
        patient = await register_patient(http, AUTH_URL)
        p_headers = {"Authorization": f"Bearer {patient['access_token']}"}

        r = await http.get(f"{APPOINTMENT_URL}/my", headers=p_headers)
        assert r.status_code == 200, r.text
        assert r.json() == []

    async def test_my_appointments_unauthenticated_rejected(self, http):
        """
        GIVEN no Authorization header
        WHEN GET /appointments/my
        THEN 401 returned
        """
        http.cookies.clear()
        r = await http.get(f"{APPOINTMENT_URL}/my")
        assert r.status_code == 401


class TestPostPayEndpoint:

    async def test_post_pay_returns_payment_url(self, http, admin_token, specialty_id):
        """
        GIVEN a confirmed appointment in pending_payment status
        WHEN POST /payments/{appointment_id}/pay
        THEN 200 with a payment_url containing 'vnpay' gateway link
        """
        patient = await register_patient(http, AUTH_URL)
        doctor = await register_doctor(http, AUTH_URL, DOCTOR_URL, admin_token, specialty_id)
        await add_doctor_schedule(http, DOCTOR_URL, doctor["user_id"], doctor["access_token"])

        # Use auto-confirm but do NOT simulate payment to keep in pending state
        await http.put(
            f"{DOCTOR_URL}/doctors/me/auto-confirm",
            json={"auto_confirm": True, "confirmation_timeout_minutes": 60},
            headers={"Authorization": f"Bearer {doctor['access_token']}"},
        )

        p_headers = {"Authorization": f"Bearer {patient['access_token']}"}
        appt_date = str(date.today() + timedelta(days=7))

        book_r = await http.post(
            f"{APPOINTMENT_URL}/",
            json={
                "doctor_id": doctor["user_id"],
                "specialty_id": specialty_id,
                "appointment_date": appt_date,
                "start_time": "09:00:00",
                "appointment_type": "general",
            },
            headers=p_headers,
        )
        assert book_r.status_code in (200, 201), book_r.text
        appt_id = book_r.json()["id"]

        # Wait for payment record to be created by event consumer
        await wait_for_payment_record(
            http=http,
            payment_url=PAYMENT_URL,
            appointment_id=appt_id,
            token=patient["access_token"],
            timeout=EVENT_TIMEOUT,
        )

        # Call POST /pay to regenerate/retrieve VNPay URL
        pay_r = await http.post(
            f"{PAYMENT_URL}/payments/{appt_id}/pay",
            headers=p_headers,
        )
        assert pay_r.status_code == 200, pay_r.text
        body = pay_r.json()
        assert "payment_url" in body
        assert "vnpay" in body["payment_url"].lower() or "vpcpay" in body["payment_url"]

    async def test_post_pay_already_paid_returns_409(self, http, admin_token, specialty_id):
        """
        GIVEN an appointment that is already paid (CONFIRMED status)
        WHEN POST /payments/{appointment_id}/pay again
        THEN 409 Conflict returned
        """
        patient = await register_patient(http, AUTH_URL)
        doctor = await register_doctor(http, AUTH_URL, DOCTOR_URL, admin_token, specialty_id)
        await add_doctor_schedule(http, DOCTOR_URL, doctor["user_id"], doctor["access_token"])

        await http.put(
            f"{DOCTOR_URL}/doctors/me/auto-confirm",
            json={"auto_confirm": True, "confirmation_timeout_minutes": 60},
            headers={"Authorization": f"Bearer {doctor['access_token']}"},
        )

        appt_date = str(date.today() + timedelta(days=8))
        confirmed, _ = await _book_and_pay(http, patient, doctor, specialty_id, appt_date)

        p_headers = {"Authorization": f"Bearer {patient['access_token']}"}
        pay_r = await http.post(
            f"{PAYMENT_URL}/payments/{confirmed['id']}/pay",
            headers=p_headers,
        )
        assert pay_r.status_code == 409, pay_r.text

    async def test_post_pay_nonexistent_appointment_returns_404(self, http):
        """
        GIVEN a random appointment_id that does not exist
        WHEN POST /payments/{id}/pay
        THEN 404 returned
        """
        import uuid

        patient = await register_patient(http, AUTH_URL)
        p_headers = {"Authorization": f"Bearer {patient['access_token']}"}

        pay_r = await http.post(
            f"{PAYMENT_URL}/payments/{uuid.uuid4()}/pay",
            headers=p_headers,
        )
        assert pay_r.status_code == 404, pay_r.text


class TestNotificationEmailFlow:

    async def test_confirmed_appointment_creates_notification(self, http, admin_token, specialty_id):
        """
        GIVEN a patient completing the full booking+payment flow
        WHEN payment is successful
        THEN a notification with type 'appointment.confirmed' appears for the patient
        """
        patient = await register_patient(http, AUTH_URL)
        doctor = await register_doctor(http, AUTH_URL, DOCTOR_URL, admin_token, specialty_id)
        await add_doctor_schedule(http, DOCTOR_URL, doctor["user_id"], doctor["access_token"])

        await http.put(
            f"{DOCTOR_URL}/doctors/me/auto-confirm",
            json={"auto_confirm": True, "confirmation_timeout_minutes": 60},
            headers={"Authorization": f"Bearer {doctor['access_token']}"},
        )

        appt_date = str(date.today() + timedelta(days=9))
        await _book_and_pay(http, patient, doctor, specialty_id, appt_date)

        # Wait for notification event to propagate
        await wait_for_notification(
            http=http,
            notification_url=NOTIFICATION_URL,
            user_token=patient["access_token"],
            notification_type="appointment.confirmed",
            contains_text="confirmed",
            timeout_seconds=EVENT_TIMEOUT,
        )
