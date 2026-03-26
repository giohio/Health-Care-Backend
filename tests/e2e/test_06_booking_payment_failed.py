"""
Test suite: Payment failure scenarios.

Covers:
  - VNPAY returns non-00 code → payment.failed
  - Appointment auto-cancelled
  - Patient notified of failure
  - Slot released (can be rebooked)
"""

import os
from datetime import date, timedelta

from tests.conftest import APPOINTMENT_URL, AUTH_URL, DOCTOR_URL, EVENT_TIMEOUT, NOTIFICATION_URL, PAYMENT_URL
from tests.helpers.auth import add_doctor_schedule, register_doctor, register_patient
from tests.helpers.vnpay_simulator import VNPaySimulator
from tests.helpers.wait import wait_for_appointment_status, wait_for_notification, wait_for_payment_record


class TestPaymentFailed:

    async def test_payment_failed_cancels_appointment(self, http, admin_token, specialty_id):
        """
        GIVEN a booking in pending_payment
        WHEN VNPAY IPN returns response_code != 00
        THEN appointment status → cancelled
        AND patient notified 'payment failed'
        AND slot is available for rebooking
        """
        patient = await register_patient(http, AUTH_URL)
        doctor = await register_doctor(http, AUTH_URL, DOCTOR_URL, admin_token, specialty_id)
        await add_doctor_schedule(http, DOCTOR_URL, doctor["user_id"], doctor["access_token"])

        today = date.today()
        days_ahead = (0 - today.weekday()) % 7 or 7
        test_date = (today + timedelta(days=days_ahead)).isoformat()

        p_header = {"Authorization": f"Bearer {patient['access_token']}"}

        # Book
        r = await http.post(
            f"{APPOINTMENT_URL}/",
            json={
                "doctor_id": doctor["user_id"],
                "specialty_id": specialty_id,
                "appointment_date": test_date,
                "start_time": "09:00",
                "appointment_type": "general",
            },
            headers=p_header,
        )
        assert r.status_code in (200, 201)
        appt_id = r.json()["id"]

        payment = await wait_for_payment_record(
            http=http,
            payment_url=PAYMENT_URL,
            appointment_id=appt_id,
            token=patient["access_token"],
            timeout=EVENT_TIMEOUT,
        )

        # Simulate FAILED payment
        vnpay = VNPaySimulator(os.getenv("VNPAY_HASH_SECRET"), PAYMENT_URL)
        await vnpay.simulate_payment(http, payment["vnpay_txn_ref"], payment["amount"], success=False)

        # Appointment should be cancelled
        await wait_for_appointment_status(
            http, APPOINTMENT_URL, appt_id, "CANCELLED", patient["access_token"], timeout=EVENT_TIMEOUT
        )

        # Patient notified
        await wait_for_notification(
            http, NOTIFICATION_URL, patient["access_token"], "payment", "failed", timeout=EVENT_TIMEOUT
        )

        # Slot is free — another patient can book same slot
        patient2 = await register_patient(http, AUTH_URL)
        r2 = await http.post(
            f"{APPOINTMENT_URL}/",
            json={
                "doctor_id": doctor["user_id"],
                "specialty_id": specialty_id,
                "appointment_date": test_date,
                "start_time": "09:00",
                "appointment_type": "general",
            },
            headers={"Authorization": f"Bearer {patient2['access_token']}"},
        )
        assert r2.status_code in (200, 201), "Slot should be available after payment failure"
