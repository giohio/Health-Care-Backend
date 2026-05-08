import os
from datetime import date, timedelta

import pytest

from tests.conftest import APPOINTMENT_URL, AUTH_URL, DOCTOR_URL, EVENT_TIMEOUT, PAYMENT_URL
from tests.helpers.auth import add_doctor_schedule, register_doctor, register_patient
from tests.helpers.vnpay_simulator import VNPaySimulator
from tests.helpers.wait import poll_until, wait_for_appointment_status, wait_for_payment_record

EMR_URL = os.getenv("EMR_URL", "http://localhost:8000")


async def _book_and_pay(http, patient, doctor, specialty_id, appointment_date):
    patient_headers = {"Authorization": f"Bearer {patient['access_token']}"}

    booked = await http.post(
        f"{APPOINTMENT_URL}/",
        json={
            "doctor_id": doctor["user_id"],
            "specialty_id": specialty_id,
            "appointment_date": appointment_date,
            "start_time": "10:00:00",
            "appointment_type": "general",
        },
        headers=patient_headers,
    )
    assert booked.status_code in (200, 201), booked.text
    appointment_id = booked.json()["id"]

    payment = await wait_for_payment_record(
        http=http,
        payment_url=PAYMENT_URL,
        appointment_id=appointment_id,
        token=patient["access_token"],
        timeout=EVENT_TIMEOUT,
    )

    simulator = VNPaySimulator(os.getenv("VNPAY_HASH_SECRET"), PAYMENT_URL)
    ipn = await simulator.simulate_payment(
        http,
        payment["vnpay_txn_ref"],
        payment["amount"],
        success=True,
    )
    assert ipn == {"RspCode": "00", "Message": "OK"}

    return await wait_for_appointment_status(
        http,
        APPOINTMENT_URL,
        appointment_id,
        "CONFIRMED",
        patient["access_token"],
        timeout=EVENT_TIMEOUT,
    )


async def _create_order_and_publish(http, doctor, patient_id, appointment_id, test_name, file_name):
    headers = {"Authorization": f"Bearer {doctor['access_token']}"}
    order = await http.post(
        f"{EMR_URL}/lab-orders",
        headers=headers,
        json={
            "patient_id": patient_id,
            "doctor_id": doctor["user_id"],
            "appointment_id": appointment_id,
            "test_name": test_name,
            "test_type": "blood_panel",
            "priority": "routine",
        },
    )
    assert order.status_code == 201, order.text

    result = await http.post(
        f"{EMR_URL}/lab-results",
        headers=headers,
        json={
            "order_id": order.json()["id"],
            "patient_id": patient_id,
            "doctor_id": doctor["user_id"],
            "file_url": f"s3://emr-bucket/{file_name}.pdf",
            "file_type": "application/pdf",
        },
    )
    assert result.status_code == 201, result.text
    result_id = result.json()["id"]

    flagged = await http.patch(f"{EMR_URL}/lab-results/{result_id}/flag-manual", headers=headers)
    assert flagged.status_code == 200, flagged.text

    verified = await http.patch(
        f"{EMR_URL}/lab-results/{result_id}/verify",
        headers=headers,
        json={
            "doctor_notes": f"Reviewed {test_name}",
            "published_text": f"{test_name} ready",
        },
    )
    assert verified.status_code == 200, verified.text


class TestLabReadinessQueueE2E:
    @pytest.mark.e2e
    async def test_doctor_queue_exposes_lab_readiness_after_all_results_publish(self, http, admin_token, specialty_id):
        patient = await register_patient(http, AUTH_URL)
        doctor = await register_doctor(http, AUTH_URL, DOCTOR_URL, admin_token, specialty_id)
        await add_doctor_schedule(http, DOCTOR_URL, doctor["user_id"], doctor["access_token"])

        await http.put(
            f"{DOCTOR_URL}/me/auto-confirm",
            json={"auto_confirm": True, "confirmation_timeout_minutes": 60},
            headers={"Authorization": f"Bearer {doctor['access_token']}"},
        )

        appointment_date = str(date.today() + timedelta(days=10))
        appointment = await _book_and_pay(http, patient, doctor, specialty_id, appointment_date)

        await _create_order_and_publish(
            http,
            doctor,
            patient["user_id"],
            appointment["id"],
            "Complete Blood Count",
            "cbc-e2e",
        )
        await _create_order_and_publish(
            http,
            doctor,
            patient["user_id"],
            appointment["id"],
            "Liver Function Test",
            "lft-e2e",
        )

        queue_response = await poll_until(
            fn=lambda: http.get(
                f"{APPOINTMENT_URL}/doctor/{doctor['user_id']}/queue",
                params={"appointment_date": appointment_date},
                headers={"Authorization": f"Bearer {doctor['access_token']}"},
            ),
            check=lambda response: response.status_code == 200 and any(
                item["appointment_id"] == appointment["id"] and item.get("lab_readiness", {}).get("all_ready") is True
                for item in response.json()
            ),
            timeout_seconds=EVENT_TIMEOUT,
            label="doctor queue lab readiness",
        )

        queue_items = queue_response.json()
        target = next(item for item in queue_items if item["appointment_id"] == appointment["id"])
        assert target["lab_readiness"]["total_orders"] == 2
        assert target["lab_readiness"]["completed_results"] == 2
        assert target["lab_readiness"]["all_ready"] is True