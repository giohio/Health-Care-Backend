import asyncio
import os
from datetime import date, timedelta
import pytest

from tests.conftest import APPOINTMENT_URL, AUTH_URL, DOCTOR_URL, PAYMENT_URL
from tests.helpers.auth import add_doctor_schedule, register_doctor, register_patient
from tests.helpers.events import publish_event
from tests.helpers.vnpay_simulator import VNPaySimulator
from tests.helpers.wait import wait_for_appointment_status


class TestAppointmentRescheduleFlow:
    """
    Verfies that rescheduling an appointment:
    1. Corrects the appointment record.
    2. Releases the original slot in the doctor's schedule.
    3. Reserves the new slot.
    """

    async def test_reschedule_lifecycle_success(self, http, admin_token, specialty_id):
        # 1. Setup Patient and Doctor
        patient = await register_patient(http, AUTH_URL)
        doctor = await register_doctor(http, AUTH_URL, DOCTOR_URL, admin_token, specialty_id)
        await add_doctor_schedule(http, DOCTOR_URL, doctor["user_id"], doctor["access_token"])

        today = date.today()
        test_date = (today + timedelta(days=1)).isoformat()
        reschedule_date = (today + timedelta(days=2)).isoformat()
        patient_h = {"Authorization": f"Bearer {patient['access_token']}"}

        # 2. Book Original Appointment (10:00)
        book = await http.post(
            f"{APPOINTMENT_URL}/",
            json={
                "doctor_id": doctor["user_id"],
                "specialty_id": specialty_id,
                "appointment_date": test_date,
                "start_time": "08:00",
                "appointment_type": "general",
            },
            headers=patient_h,
        )
        assert book.status_code in (200, 201)
        appointment_id = book.json()["id"]

        # 3. Pay to reach CONFIRMED
        payment = None
        for _ in range(20):
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
        
        await wait_for_appointment_status(
            http, APPOINTMENT_URL, appointment_id, "CONFIRMED", patient["access_token"], timeout_seconds=45
        )

        # 4. Verify Original Slot is Taken
        slots_resp = await http.get(
            f"{APPOINTMENT_URL}/doctor/{doctor['user_id']}/slots?appointment_date={test_date}&specialty_id={specialty_id}",
            headers=patient_h
        )
        slots = slots_resp.json()["slots"]
        assert any(s["start_time"].startswith("08:00") and not s.get("is_available") for s in slots)

        # 5. Reschedule
        resched_resp = await http.put(
            f"{APPOINTMENT_URL}/{appointment_id}/reschedule",
            json={
                "new_date": reschedule_date,
                "new_time": "09:10",
            },
            headers=patient_h
        )
        assert resched_resp.status_code == 200

        # 6. Verify Old Slot is Released (Polled)
        for _ in range(10):
            slots_old_resp = await http.get(
                f"{APPOINTMENT_URL}/doctor/{doctor['user_id']}/slots?appointment_date={test_date}&specialty_id={specialty_id}",
                headers=patient_h
            )
            assert slots_old_resp.status_code == 200
            slots_old = slots_old_resp.json()["slots"]
            if any(s["start_time"].startswith("08:00") and s.get("is_available") for s in slots_old):
                break
            await asyncio.sleep(1)
        else:
            pytest.fail(f"Original slot 08:00 was never released after reschedule")

        # 7. Verify New Slot is Taken
        slots_new_resp = await http.get(
            f"{APPOINTMENT_URL}/doctor/{doctor['user_id']}/slots?appointment_date={reschedule_date}&specialty_id={specialty_id}",
            headers=patient_h
        )
        slots_new = slots_new_resp.json()["slots"]
        assert any(s["start_time"].startswith("09:10") and not s.get("is_available") for s in slots_new)

        # 8. Verify queue cache is refreshed: old date queue no longer contains appointment,
        # and new date queue contains the rescheduled appointment.
        old_queue_resp = await http.get(
            f"{APPOINTMENT_URL}/doctor/{doctor['user_id']}/queue?appointment_date={test_date}",
            headers=patient_h,
        )
        assert old_queue_resp.status_code == 200
        old_queue = old_queue_resp.json()
        assert all(item.get("appointment_id") != appointment_id for item in old_queue)

        new_queue_resp = await http.get(
            f"{APPOINTMENT_URL}/doctor/{doctor['user_id']}/queue?appointment_date={reschedule_date}",
            headers=patient_h,
        )
        assert new_queue_resp.status_code == 200
        new_queue = new_queue_resp.json()
        assert any(item.get("appointment_id") == appointment_id for item in new_queue)
