"""
Test suite: Cancellation and refund flows.

Covers:
  - Patient cancels confirmed appointment
    → refund triggered
  - Doctor cancels confirmed appointment
    → patient notified + refund
  - Cancel pending_payment appointment
    → no refund needed
"""

import os
from datetime import date, timedelta

from tests.conftest import APPOINTMENT_URL, AUTH_URL, DOCTOR_URL, EVENT_TIMEOUT, NOTIFICATION_URL, PAYMENT_URL
from tests.helpers.auth import add_doctor_schedule, register_doctor, register_patient
from tests.helpers.vnpay_simulator import VNPaySimulator
from tests.helpers.wait import wait_for_appointment_status, wait_for_notification, wait_for_payment_record


class TestCancelWithRefund:

    async def test_patient_cancel_after_confirm(self, http, admin_token, specialty_id):
        """
        GIVEN a confirmed appointment (payment paid)
        WHEN patient cancels
        THEN appointment → cancelled
        AND payment → refunded
        AND doctor notified
        """
        # Setup: full booking + auto-confirm flow
        patient = await register_patient(http, AUTH_URL)
        doctor = await register_doctor(http, AUTH_URL, DOCTOR_URL, admin_token, specialty_id)
        await add_doctor_schedule(http, DOCTOR_URL, doctor["user_id"], doctor["access_token"])

        today = date.today()
        days_ahead = (0 - today.weekday()) % 7 or 7
        test_date = (today + timedelta(days=days_ahead)).isoformat()
        p_header = {"Authorization": f"Bearer {patient['access_token']}"}

        # Book + pay
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
        appt_id = r.json()["id"]

        payment = await wait_for_payment_record(
            http=http,
            payment_url=PAYMENT_URL,
            appointment_id=appt_id,
            token=patient["access_token"],
            timeout=EVENT_TIMEOUT,
        )
        vnpay = VNPaySimulator(os.getenv("VNPAY_HASH_SECRET"), PAYMENT_URL)
        await vnpay.simulate_payment(http, payment["vnpay_txn_ref"], payment["amount"], success=True)

        # Wait for confirmed
        await wait_for_appointment_status(
            http, APPOINTMENT_URL, appt_id, "confirmed", patient["access_token"], timeout=EVENT_TIMEOUT
        )

        # Patient cancels
        r = await http.put(f"{APPOINTMENT_URL}/{appt_id}/cancel", json={"reason": "Change of plans"}, headers=p_header)
        assert r.status_code == 200

        # Appointment cancelled
        await wait_for_appointment_status(
            http, APPOINTMENT_URL, appt_id, "cancelled", patient["access_token"], timeout=EVENT_TIMEOUT
        )

        # Payment refunded
        from tests.helpers.wait import wait_for_payment_status
        payment_after = await wait_for_payment_status(
            http, PAYMENT_URL, appt_id, ("refunded", "refund_pending"), patient["access_token"], timeout=EVENT_TIMEOUT
        )
        assert payment_after["status"] in ("refunded", "refund_pending")

        # Doctor notified of cancellation
        await wait_for_notification(
            http, NOTIFICATION_URL, doctor["access_token"], "appointment", "Cancelled", timeout=EVENT_TIMEOUT
        )
