"""
Integration: booking -> payment record -> VNPay failed IPN -> appointment cancelled.
"""

import os
from datetime import date, timedelta

from tests.conftest import APPOINTMENT_URL, AUTH_URL, DOCTOR_URL, EVENT_TIMEOUT, PAYMENT_URL
from tests.helpers.auth import add_doctor_schedule, register_doctor, register_patient
from tests.helpers.vnpay_simulator import VNPaySimulator
from tests.helpers.wait import wait_for_appointment_status


class TestPaymentFailedPathIntegration:
    async def test_payment_failed_cancels_appointment(self, http, admin_token, specialty_id):
        patient = await register_patient(http, AUTH_URL)
        doctor = await register_doctor(http, AUTH_URL, DOCTOR_URL, admin_token, specialty_id)
        await add_doctor_schedule(http, DOCTOR_URL, doctor["user_id"], doctor["access_token"])

        today = date.today()
        days_ahead = (0 - today.weekday()) % 7 or 7
        test_date = (today + timedelta(days=days_ahead)).isoformat()

        patient_h = {"Authorization": f"Bearer {patient['access_token']}"}

        book = await http.post(
            f"{APPOINTMENT_URL}/",
            json={
                "doctor_id": doctor["user_id"],
                "specialty_id": specialty_id,
                "appointment_date": test_date,
                "start_time": "10:00",
                "appointment_type": "general",
            },
            headers=patient_h,
        )
        assert book.status_code in (200, 201), book.text
        appointment_id = book.json()["id"]

        payment_resp = None
        for _ in range(20):
            payment_resp = await http.get(f"{PAYMENT_URL}/payments/{appointment_id}", headers=patient_h)
            if payment_resp.status_code == 200:
                break
            import asyncio

            await asyncio.sleep(0.5)

        assert payment_resp is not None and payment_resp.status_code == 200, (
            payment_resp.text if payment_resp is not None else "No payment response"
        )
        payment = payment_resp.json()

        vnpay = VNPaySimulator(os.getenv("VNPAY_HASH_SECRET"), PAYMENT_URL)
        ipn = await vnpay.simulate_payment(
            http=http,
            txn_ref=payment["vnpay_txn_ref"],
            amount=payment["amount"],
            success=False,
        )
        assert ipn.get("RspCode") == "00", ipn

        cancelled = await wait_for_appointment_status(
            http=http,
            appointment_url=APPOINTMENT_URL,
            appointment_id=appointment_id,
            expected_status="CANCELLED",
            token=patient["access_token"],
            timeout=EVENT_TIMEOUT,
        )
        assert cancelled["status"] == "CANCELLED"
