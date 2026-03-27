import asyncio
import os
from datetime import date, timedelta
import pytest

from tests.conftest import APPOINTMENT_URL, AUTH_URL, DOCTOR_URL, EVENT_TIMEOUT, PAYMENT_URL
from tests.helpers.auth import add_doctor_schedule, register_doctor, register_patient
from tests.helpers.events import publish_event
from tests.helpers.vnpay_simulator import VNPaySimulator
from tests.helpers.wait import wait_for_appointment_status


class TestDoctorClinicalFlow:
    """
    Verifies the full clinical lifecycle:
    Book -> Paid -> Confirmed -> Start -> Complete
    """

    async def test_full_clinical_workflow_success(self, http, admin_token, specialty_id):
        # 1. Setup Patient and Doctor
        patient = await register_patient(http, AUTH_URL)
        doctor = await register_doctor(http, AUTH_URL, DOCTOR_URL, admin_token, specialty_id)
        await add_doctor_schedule(http, DOCTOR_URL, doctor["user_id"], doctor["access_token"])

        today = date.today()
        test_date = (today + timedelta(days=1)).isoformat()
        patient_h = {"Authorization": f"Bearer {patient['access_token']}"}
        doctor_h = {"Authorization": f"Bearer {doctor['access_token']}"}

        # 2. Book Appointment
        book = await http.post(
            f"{APPOINTMENT_URL}/",
            json={
                "doctor_id": doctor["user_id"],
                "specialty_id": specialty_id,
                "appointment_date": test_date,
                "start_time": "16:00",
                "appointment_type": "general",
            },
            headers=patient_h,
        )
        assert book.status_code in (200, 201)
        appointment_id = book.json()["id"]

        # 3. Pay for Appointment (Hit IPN + Direct Event Publication)
        payment = None
        for _ in range(10):
            resp = await http.get(f"{PAYMENT_URL}/payments/{appointment_id}", headers=patient_h)
            if resp.status_code == 200:
                payment = resp.json()
                break
            await asyncio.sleep(0.5)
        
        vnpay = VNPaySimulator(os.getenv("VNPAY_HASH_SECRET"), PAYMENT_URL)
        await vnpay.simulate_payment(http, payment["vnpay_txn_ref"], payment["amount"], success=True)
        
        # Publish event directly to ensure Appointment Service processes it immediately
        await publish_event(
            exchange="payment_events",
            routing_key="payment.paid",
            payload={
                "payment_id": str(payment["id"]),
                "appointment_id": str(appointment_id),
                "patient_id": str(patient["user_id"]),
                "doctor_id": str(doctor["user_id"]),
                "status": "paid",
            }
        )

        # 4. Wait for CONFIRMED
        await wait_for_appointment_status(
            http, APPOINTMENT_URL, appointment_id, "CONFIRMED", patient["access_token"], timeout_seconds=45
        )

        # 5. Doctor Starts Appointment
        start_resp = await http.put(
            f"{APPOINTMENT_URL}/{appointment_id}/start",
            headers=doctor_h
        )
        assert start_resp.status_code == 200
        assert start_resp.json()["status"] == "IN_PROGRESS"

        # 6. Verify Queue Status (Polled due to projection latency)
        for _ in range(10):
            queue_resp = await http.get(
                f"{APPOINTMENT_URL}/doctor/{doctor['user_id']}/queue?date={test_date}",
                headers=doctor_h
            )
            assert queue_resp.status_code == 200
            queue = queue_resp.json()
            if any(item["appointment_id"] == appointment_id and item["status"] == "IN_PROGRESS" for item in queue):
                break
            await asyncio.sleep(1)
        else:
            pytest.fail(f"Appointment {appointment_id} never appeared as IN_PROGRESS in doctor queue")

        # 7. Doctor Completes Appointment
        complete_resp = await http.put(
            f"{APPOINTMENT_URL}/{appointment_id}/complete",
            headers=doctor_h
        )
        assert complete_resp.status_code == 200
        assert complete_resp.json()["status"] == "COMPLETED"

        # 8. Final verify
        final_appt = await http.get(f"{APPOINTMENT_URL}/{appointment_id}", headers=patient_h)
        assert final_appt.json()["status"] == "COMPLETED"
