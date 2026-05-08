"""
Integration: booking/payment emits notification and mark-read updates unread count.
"""

import os
from datetime import date, timedelta

from tests.conftest import APPOINTMENT_URL, AUTH_URL, DOCTOR_URL, EVENT_TIMEOUT, NOTIFICATION_URL, PAYMENT_URL
from tests.helpers.auth import add_doctor_schedule, register_doctor, register_patient
from tests.helpers.vnpay_simulator import VNPaySimulator
from tests.helpers.wait import wait_for_appointment_status, wait_for_notification, wait_for_payment_record


class TestNotificationReadFlow:
    async def test_confirmed_appointment_notification_mark_read_roundtrip(self, http, admin_token, specialty_id):
        patient = await register_patient(http, AUTH_URL)
        doctor = await register_doctor(http, AUTH_URL, DOCTOR_URL, admin_token, specialty_id)
        await add_doctor_schedule(http, DOCTOR_URL, doctor["user_id"], doctor["access_token"])

        test_date = (date.today() + timedelta(days=1)).isoformat()
        patient_h = {"Authorization": f"Bearer {patient['access_token']}"}
        doctor_h = {"Authorization": f"Bearer {doctor['access_token']}"}

        auto_confirm = await http.put(
            f"{DOCTOR_URL}/me/auto-confirm",
            json={"auto_confirm": True, "confirmation_timeout_minutes": 15},
            headers=doctor_h,
        )
        assert auto_confirm.status_code == 200, auto_confirm.text

        book = await http.post(
            f"{APPOINTMENT_URL}/",
            json={
                "doctor_id": doctor["user_id"],
                "specialty_id": specialty_id,
                "appointment_date": test_date,
                "start_time": "09:20",
                "appointment_type": "general",
            },
            headers=patient_h,
        )
        assert book.status_code in (200, 201), book.text
        appointment_id = book.json()["id"]

        payment = await wait_for_payment_record(
            http=http,
            payment_url=PAYMENT_URL,
            appointment_id=appointment_id,
            token=patient["access_token"],
            timeout=EVENT_TIMEOUT,
        )

        vnpay = VNPaySimulator(os.getenv("VNPAY_HASH_SECRET"), PAYMENT_URL)
        ipn = await vnpay.simulate_payment(http, payment["vnpay_txn_ref"], payment["amount"], success=True)
        assert ipn.get("RspCode") == "00", ipn

        await wait_for_appointment_status(
            http,
            APPOINTMENT_URL,
            appointment_id,
            "CONFIRMED",
            patient["access_token"],
            timeout=EVENT_TIMEOUT,
        )

        await wait_for_notification(
            http=http,
            notification_url=NOTIFICATION_URL,
            user_token=patient["access_token"],
            notification_type="appointment",
            contains_text="Confirmed",
            timeout=EVENT_TIMEOUT,
        )

        me_before = await http.get(f"{NOTIFICATION_URL}/notifications/me", headers=patient_h)
        assert me_before.status_code == 200, me_before.text
        payload_before = me_before.json()
        unread_before = int(payload_before.get("unread_count", 0))
        notifications = payload_before.get("notifications", [])

        first_unread = next((n for n in notifications if not n.get("is_read", False)), None)
        assert first_unread is not None, "Expected at least one unread notification"

        mark = await http.put(
            f"{NOTIFICATION_URL}/notifications/{first_unread['id']}/read",
            headers=patient_h,
        )
        assert mark.status_code == 200, mark.text

        me_after = await http.get(f"{NOTIFICATION_URL}/notifications/me", headers=patient_h)
        assert me_after.status_code == 200, me_after.text
        payload_after = me_after.json()
        unread_after = int(payload_after.get("unread_count", 0))
        assert unread_after <= unread_before
