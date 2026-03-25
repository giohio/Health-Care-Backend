"""
Test suite: Booking with auto_confirm=False.

Covers:
  - Payment paid → appointment goes to PENDING
    (not auto-confirmed)
  - Doctor sees new booking in queue
  - Doctor confirms → patient notified
  - Doctor declines → patient notified + refund triggered
"""

import os
from datetime import date, timedelta

from tests.conftest import APPOINTMENT_URL, AUTH_URL, DOCTOR_URL, EVENT_TIMEOUT, NOTIFICATION_URL, PAYMENT_URL
from tests.helpers.auth import add_doctor_schedule, register_doctor, register_patient
from tests.helpers.vnpay_simulator import VNPaySimulator
from tests.helpers.wait import wait_for_appointment_status, wait_for_notification, wait_for_payment_record


class TestBookingManualConfirm:

    async def test_manual_confirm_flow(self, http, admin_token, specialty_id):
        """
        GIVEN doctor has auto_confirm=False
        WHEN patient books + pays
        THEN appointment goes to PENDING (not confirmed)
        WHEN doctor confirms
        THEN appointment becomes CONFIRMED
        AND patient notified with queue number
        """
        patient = await register_patient(http, AUTH_URL)
        doctor = await register_doctor(http, AUTH_URL, DOCTOR_URL, admin_token, specialty_id)
        await add_doctor_schedule(http, DOCTOR_URL, doctor["user_id"], doctor["access_token"])
        # Disable auto_confirm
        await http.put(
            f"{DOCTOR_URL}/me/auto-confirm",
            json={"auto_confirm": False, "confirmation_timeout_minutes": 15},
            headers={"Authorization": f"Bearer {doctor['access_token']}"},
        )

        today = date.today()
        days_ahead = (0 - today.weekday()) % 7 or 7
        test_date = (today + timedelta(days=days_ahead)).isoformat()

        p_header = {"Authorization": f"Bearer {patient['access_token']}"}
        d_header = {"Authorization": f"Bearer {doctor['access_token']}"}
        vnpay = VNPaySimulator(
            hash_secret=os.getenv("VNPAY_HASH_SECRET"),
            payment_url=PAYMENT_URL,
        )

        # Book
        r = await http.post(
            f"{APPOINTMENT_URL}/",
            json={
                "doctor_id": doctor["user_id"],
                "specialty_id": specialty_id,
                "appointment_date": test_date,
                "start_time": "10:00",
                "appointment_type": "general",
            },
            headers=p_header,
        )
        appt_id = r.json()["id"]

        # Get payment + simulate IPN
        payment = await wait_for_payment_record(
            http=http,
            payment_url=PAYMENT_URL,
            appointment_id=appt_id,
            token=patient["access_token"],
            timeout=EVENT_TIMEOUT,
        )
        await vnpay.simulate_payment(http, payment["vnpay_txn_ref"], payment["amount"], success=True)

        # Must be PENDING (not confirmed) after payment
        pending = await wait_for_appointment_status(
            http, APPOINTMENT_URL, appt_id, "pending", patient["access_token"], timeout=EVENT_TIMEOUT
        )
        assert pending["status"] == "pending"

        # Doctor confirms
        r = await http.put(f"{APPOINTMENT_URL}/{appt_id}/confirm", headers=d_header)
        assert r.status_code == 200

        # Appointment confirmed
        confirmed = await wait_for_appointment_status(
            http, APPOINTMENT_URL, appt_id, "confirmed", patient["access_token"], timeout=EVENT_TIMEOUT
        )
        assert confirmed["queue_number"] >= 1

        # Patient notified
        await wait_for_notification(
            http, NOTIFICATION_URL, patient["access_token"], "appointment", "Confirmed", timeout=EVENT_TIMEOUT
        )

    async def test_doctor_decline_triggers_refund(self, http, admin_token, specialty_id):
        """
        GIVEN appointment in PENDING (post-payment)
        WHEN doctor declines
        THEN appointment is CANCELLED
        AND payment refund is triggered
        AND patient notified of decline
        """
        patient = await register_patient(http, AUTH_URL)
        doctor = await register_doctor(http, AUTH_URL, DOCTOR_URL, admin_token, specialty_id)
        await add_doctor_schedule(http, DOCTOR_URL, doctor["user_id"], doctor["access_token"])
        # Disable auto_confirm
        await http.put(
            f"{DOCTOR_URL}/me/auto-confirm",
            json={"auto_confirm": False, "confirmation_timeout_minutes": 15},
            headers={"Authorization": f"Bearer {doctor['access_token']}"},
        )

        today = date.today()
        days_ahead = (0 - today.weekday()) % 7 or 7
        test_date = (today + timedelta(days=days_ahead)).isoformat()

        p_header = {"Authorization": f"Bearer {patient['access_token']}"}
        d_header = {"Authorization": f"Bearer {doctor['access_token']}"}
        vnpay = VNPaySimulator(
            hash_secret=os.getenv("VNPAY_HASH_SECRET"),
            payment_url=PAYMENT_URL,
        )

        r = await http.post(
            f"{APPOINTMENT_URL}/",
            json={
                "doctor_id": doctor["user_id"],
                "specialty_id": specialty_id,
                "appointment_date": test_date,
                "start_time": "11:00",
                "appointment_type": "general",
            },
            headers=p_header,
        )
        appt_id = r.json()["id"]

        payment = await wait_for_payment_record(
            http=http,
            payment_url=PAYMENT_URL,
            appointment_id=appt_id,
            token=patient["access_token"],
            timeout=EVENT_TIMEOUT,
        )
        await vnpay.simulate_payment(http, payment["vnpay_txn_ref"], payment["amount"], success=True)

        await wait_for_appointment_status(
            http, APPOINTMENT_URL, appt_id, "pending", patient["access_token"], timeout=EVENT_TIMEOUT
        )

        # Doctor declines
        r = await http.put(
            f"{APPOINTMENT_URL}/{appt_id}/decline", json={"reason": "Schedule conflict"}, headers=d_header
        )
        assert r.status_code == 200

        # Appointment cancelled (declined)
        await wait_for_appointment_status(
            http, APPOINTMENT_URL, appt_id, "declined", patient["access_token"], timeout=EVENT_TIMEOUT
        )

        # Patient notified of decline
        await wait_for_notification(
            http, NOTIFICATION_URL, patient["access_token"], "appointment", "Declined", timeout=EVENT_TIMEOUT
        )

        # Payment refund triggered
        payment_after = (await http.get(f"{PAYMENT_URL}/payments/{appt_id}", headers=p_header)).json()
        assert payment_after["status"] in ("refunded", "refund_pending")
