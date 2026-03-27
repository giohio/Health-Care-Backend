import asyncio
import os
from datetime import date, timedelta

from tests.conftest import APPOINTMENT_URL, AUTH_URL, DOCTOR_URL, EVENT_TIMEOUT, PAYMENT_URL
from tests.helpers.auth import add_doctor_schedule, register_doctor, register_patient
from tests.helpers.events import publish_event
from tests.helpers.vnpay_simulator import VNPaySimulator
from tests.helpers.wait import wait_for_appointment_status


class TestPaymentExpiryRefundIntegration:
    """
    Verfies that Appointment Service correctly handles expiry and refund 
    events emitted by the Payment Service or other producers.
    """

    async def test_payment_expiry_cancels_appointment(self, http, admin_token, specialty_id):
        # 1. Setup Appointment
        patient = await register_patient(http, AUTH_URL)
        doctor = await register_doctor(http, AUTH_URL, DOCTOR_URL, admin_token, specialty_id)
        await add_doctor_schedule(http, DOCTOR_URL, doctor["user_id"], doctor["access_token"])

        today = date.today()
        test_date = (today + timedelta(days=1)).isoformat()
        patient_h = {"Authorization": f"Bearer {patient['access_token']}"}

        book = await http.post(
            f"{APPOINTMENT_URL}/",
            json={
                "doctor_id": doctor["user_id"],
                "specialty_id": specialty_id,
                "appointment_date": test_date,
                "start_time": "14:00",
                "appointment_type": "general",
            },
            headers=patient_h,
        )
        assert book.status_code in (200, 201)
        appointment_id = book.json()["id"]

        # 2. Wait for Payment record to exist
        payment = None
        for _ in range(10):
            resp = await http.get(f"{PAYMENT_URL}/payments/{appointment_id}", headers=patient_h)
            if resp.status_code == 200:
                payment = resp.json()
                break
            await asyncio.sleep(0.5)
        assert payment is not None

        # 3. Simulate Payment Expiry (Simulate Payment Service producing the event)
        await publish_event(
            exchange="payment_events",
            routing_key="payment.expired",
            payload={
                "payment_id": str(payment["id"]),
                "appointment_id": str(appointment_id),
                "patient_id": str(patient["user_id"]),
                "doctor_id": str(doctor["user_id"]),
            }
        )

        # 4. Verify Appointment is CANCELLED by system
        cancelled = await wait_for_appointment_status(
            http=http,
            appointment_url=APPOINTMENT_URL,
            appointment_id=appointment_id,
            expected_status="CANCELLED",
            token=patient["access_token"],
            timeout=EVENT_TIMEOUT,
        )
        assert cancelled["status"] == "CANCELLED"

    async def test_appointment_cancellation_triggers_refund_requested(self, http, admin_token, specialty_id):
        # 1. Setup PAID Appointment
        patient = await register_patient(http, AUTH_URL)
        doctor = await register_doctor(http, AUTH_URL, DOCTOR_URL, admin_token, specialty_id)
        await add_doctor_schedule(http, DOCTOR_URL, doctor["user_id"], doctor["access_token"])

        test_date = (date.today() + timedelta(days=2)).isoformat()
        patient_h = {"Authorization": f"Bearer {patient['access_token']}"}

        book = await http.post(
            f"{APPOINTMENT_URL}/",
            json={
                "doctor_id": doctor["user_id"],
                "specialty_id": specialty_id,
                "appointment_date": test_date,
                "start_time": "15:00",
                "appointment_type": "general",
            },
            headers=patient_h,
        )
        appointment_id = book.json()["id"]

        # Wait for payment and mark as PAID
        payment = None
        for _ in range(10):
            resp = await http.get(f"{PAYMENT_URL}/payments/{appointment_id}", headers=patient_h)
            if resp.status_code == 200:
                payment = resp.json()
                break
            await asyncio.sleep(0.5)
        
        vnpay = VNPaySimulator(os.getenv("VNPAY_HASH_SECRET"), PAYMENT_URL)
        await vnpay.simulate_payment(http, payment["vnpay_txn_ref"], payment["amount"], success=True)
        
        # Wait for CONFIRMED
        await wait_for_appointment_status(
            http, APPOINTMENT_URL, appointment_id, "CONFIRMED", patient["access_token"]
        )

        # 2. Cancel the appointment (as patient)
        cancel_resp = await http.put(
            f"{APPOINTMENT_URL}/{appointment_id}/cancel",
            json={"reason": "User changed mind"},
            headers=patient_h
        )
        assert cancel_resp.status_code == 200
        assert cancel_resp.json()["payment_status"] == "REFUNDED" # In current code, status transitions to REFUNDED immediately in app_service

        # 3. Verify Payment Service processes the refund requested
        # We poll the payment record in Payment Service to see if its internal status becomes 'refunded'
        # PaymentRefundRequestedConsumer transitions status to 'refunded'
        refunded_payment = None
        for _ in range(20):
            resp = await http.get(f"{PAYMENT_URL}/payments/{appointment_id}", headers=patient_h)
            if resp.status_code == 200:
                if resp.json().get("status") == "refunded":
                    refunded_payment = resp.json()
                    break
            await asyncio.sleep(0.5)
        
        assert refunded_payment is not None
        assert refunded_payment["status"] == "refunded"
