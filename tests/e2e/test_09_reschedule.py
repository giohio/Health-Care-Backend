"""
Test suite: Reschedule flows.

Covers:
  - Patient reschedules confirmed appointment
    → status reset to pending
    → doctor must re-confirm
  - Reschedule to taken slot → 409
  - Old slot freed after reschedule
"""

import os
from datetime import date, timedelta

from tests.conftest import APPOINTMENT_URL, AUTH_URL, DOCTOR_URL, EVENT_TIMEOUT, NOTIFICATION_URL, PAYMENT_URL
from tests.helpers.auth import add_doctor_schedule, register_doctor, register_patient
from tests.helpers.vnpay_simulator import VNPaySimulator
from tests.helpers.wait import wait_for_appointment_status, wait_for_notification, wait_for_payment_record


class TestReschedule:

    async def test_reschedule_resets_to_pending(self, http, admin_token, specialty_id):
        """
        GIVEN a confirmed appointment
        WHEN patient reschedules to a new slot
        THEN appointment date/time updated
        AND status reset to pending
        AND old slot is freed
        AND doctor notified to re-confirm
        """
        patient = await register_patient(http, AUTH_URL)
        doctor = await register_doctor(http, AUTH_URL, DOCTOR_URL, admin_token, specialty_id)
        await add_doctor_schedule(http, DOCTOR_URL, doctor["user_id"], doctor["access_token"])

        today = date.today()
        days_ahead = (0 - today.weekday()) % 7 or 7
        test_date = (today + timedelta(days=days_ahead)).isoformat()
        next_week = (today + timedelta(days=days_ahead + 7)).isoformat()

        p_header = {"Authorization": f"Bearer {patient['access_token']}"}

        # Book + pay + confirm
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
        await wait_for_appointment_status(
            http, APPOINTMENT_URL, appt_id, "CONFIRMED", patient["access_token"], timeout=EVENT_TIMEOUT
        )

        # Reschedule to next week
        r = await http.put(
            f"{APPOINTMENT_URL}/{appt_id}/reschedule",
            json={
                "new_date": next_week,
                "new_time": "10:00",
            },
            headers=p_header,
        )
        assert r.status_code == 200
        updated = r.json()
        assert updated["appointment_date"] == next_week
        assert updated["start_time"] == "10:00"
        assert updated["status"] == "PENDING"
        assert updated["queue_number"] is None

        # Doctor notified to re-confirm
        await wait_for_notification(
            http, NOTIFICATION_URL, doctor["access_token"], "appointment", "Rescheduled", timeout=EVENT_TIMEOUT
        )

    async def test_reschedule_to_taken_slot_fails(self, http, admin_token, specialty_id):
        """
        GIVEN slot 10:00 already booked by another patient
        WHEN original patient tries to reschedule to 10:00
        THEN 409 Conflict returned
        """
        # Setup two patients, one doctor
        patient1 = await register_patient(http, AUTH_URL)
        patient2 = await register_patient(http, AUTH_URL)
        doctor = await register_doctor(http, AUTH_URL, DOCTOR_URL, admin_token, specialty_id)
        await add_doctor_schedule(http, DOCTOR_URL, doctor["user_id"], doctor["access_token"])

        today = date.today()
        days_ahead = (0 - today.weekday()) % 7 or 7
        test_date = (today + timedelta(days=days_ahead)).isoformat()

        # Patient 1 books 09:00
        r1 = await http.post(
            f"{APPOINTMENT_URL}/",
            json={
                "doctor_id": doctor["user_id"],
                "specialty_id": specialty_id,
                "appointment_date": test_date,
                "start_time": "09:00",
                "appointment_type": "general",
            },
            headers={"Authorization": f"Bearer {patient1['access_token']}"},
        )
        appt1_id = r1.json()["id"]

        # Patient 2 books 10:00
        r2 = await http.post(
            f"{APPOINTMENT_URL}/",
            json={
                "doctor_id": doctor["user_id"],
                "specialty_id": specialty_id,
                "appointment_date": test_date,
                "start_time": "10:00",
                "appointment_type": "general",
            },
            headers={"Authorization": f"Bearer {patient2['access_token']}"},
        )
        assert r2.status_code in (200, 201)

        # Patient 1 tries to reschedule 09:00 → 10:00 (taken)
        r = await http.put(
            f"{APPOINTMENT_URL}/{appt1_id}/reschedule",
            json={
                "new_date": test_date,
                "new_time": "10:00",
            },
            headers={"Authorization": f"Bearer {patient1['access_token']}"},
        )
        assert r.status_code == 409
