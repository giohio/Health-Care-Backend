import os
from datetime import date, timedelta

import pytest

from tests.conftest import APPOINTMENT_URL, AUTH_URL, DOCTOR_URL, EVENT_TIMEOUT, NOTIFICATION_URL, PAYMENT_URL
from tests.helpers.auth import add_doctor_schedule, register_doctor, register_patient
from tests.helpers.vnpay_simulator import VNPaySimulator
from tests.helpers.wait import poll_until, wait_for_appointment_status, wait_for_notification, wait_for_payment_record

EMR_URL = os.getenv("EMR_URL", "http://localhost:8000")


async def _book_and_pay(http, patient, doctor, specialty_id, appointment_date):
    patient_headers = {"Authorization": f"Bearer {patient['access_token']}"}

    booked = await http.post(
        f"{APPOINTMENT_URL}/",
        json={
            "doctor_id": doctor["user_id"],
            "specialty_id": specialty_id,
            "appointment_date": appointment_date,
            "start_time": "09:00:00",
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

    confirmed = await wait_for_appointment_status(
        http,
        APPOINTMENT_URL,
        appointment_id,
        "CONFIRMED",
        patient["access_token"],
        timeout=EVENT_TIMEOUT,
    )
    return confirmed


async def _create_lab_order(http, doctor_token, patient_id, doctor_id, appointment_id, test_name, fee=0):
    response = await http.post(
        f"{EMR_URL}/lab-orders",
        headers={"Authorization": f"Bearer {doctor_token}"},
        json={
            "patient_id": patient_id,
            "doctor_id": doctor_id,
            "appointment_id": appointment_id,
            "test_name": test_name,
            "test_type": "blood_panel",
            "priority": "routine",
            "fee": fee,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _upload_and_publish_result(http, doctor_token, order, patient_id, doctor_id, file_name):
    headers = {"Authorization": f"Bearer {doctor_token}"}
    uploaded = await http.post(
        f"{EMR_URL}/lab-results",
        headers=headers,
        json={
            "order_id": order["id"],
            "patient_id": patient_id,
            "doctor_id": doctor_id,
            "file_url": f"s3://emr-bucket/{file_name}.pdf",
            "file_type": "application/pdf",
        },
    )
    assert uploaded.status_code == 201, uploaded.text
    result_id = uploaded.json()["id"]

    flagged = await http.patch(f"{EMR_URL}/lab-results/{result_id}/flag-manual", headers=headers)
    assert flagged.status_code == 200, flagged.text

    verified = await http.patch(
        f"{EMR_URL}/lab-results/{result_id}/verify",
        headers=headers,
        json={
            "doctor_notes": f"Reviewed {order['test_name']}",
            "published_text": f"{order['test_name']} is ready.",
        },
    )
    assert verified.status_code == 200, verified.text
    return verified.json()


class TestLabReadinessIntegration:
    @pytest.mark.integration
    async def test_lab_payment_notification_and_readiness_events(self, http, admin_token, specialty_id):
        patient = await register_patient(http, AUTH_URL)
        doctor = await register_doctor(http, AUTH_URL, DOCTOR_URL, admin_token, specialty_id)
        await add_doctor_schedule(http, DOCTOR_URL, doctor["user_id"], doctor["access_token"])

        await http.put(
            f"{DOCTOR_URL}/me/auto-confirm",
            json={"auto_confirm": True, "confirmation_timeout_minutes": 60},
            headers={"Authorization": f"Bearer {doctor['access_token']}"},
        )

        appointment_date = str(date.today() + timedelta(days=9))
        appointment = await _book_and_pay(http, patient, doctor, specialty_id, appointment_date)

        payable_order = await _create_lab_order(
            http,
            doctor["access_token"],
            patient["user_id"],
            doctor["user_id"],
            appointment["id"],
            "Metabolic Panel",
            fee=225000,
        )

        await wait_for_notification(
            http,
            NOTIFICATION_URL,
            patient["access_token"],
            "payment.created",
            "Lab Order Payment Ready",
            timeout=EVENT_TIMEOUT,
        )

        first_order = await _create_lab_order(
            http,
            doctor["access_token"],
            patient["user_id"],
            doctor["user_id"],
            appointment["id"],
            "Complete Blood Count",
        )
        second_order = await _create_lab_order(
            http,
            doctor["access_token"],
            patient["user_id"],
            doctor["user_id"],
            appointment["id"],
            "Liver Function Test",
        )

        initial_readiness = await http.get(
            f"{EMR_URL}/lab-orders/{appointment['id']}/readiness",
            headers={"Authorization": f"Bearer {doctor['access_token']}"},
        )
        assert initial_readiness.status_code == 200, initial_readiness.text
        assert initial_readiness.json()["total_orders"] == 3
        assert initial_readiness.json()["completed_results"] == 0
        assert initial_readiness.json()["all_ready"] is False

        await _upload_and_publish_result(
            http,
            doctor["access_token"],
            first_order,
            patient["user_id"],
            doctor["user_id"],
            "cbc-result",
        )

        await wait_for_notification(
            http,
            NOTIFICATION_URL,
            patient["access_token"],
            "lab_result.published",
            "Lab Result Ready",
            timeout=EVENT_TIMEOUT,
        )

        partial_readiness = await http.get(
            f"{EMR_URL}/lab-orders/{appointment['id']}/readiness",
            headers={"Authorization": f"Bearer {doctor['access_token']}"},
        )
        assert partial_readiness.status_code == 200, partial_readiness.text
        partial_payload = partial_readiness.json()
        assert partial_payload["total_orders"] == 3
        assert partial_payload["completed_results"] == 1
        assert partial_payload["all_ready"] is False

        await _upload_and_publish_result(
            http,
            doctor["access_token"],
            second_order,
            patient["user_id"],
            doctor["user_id"],
            "lft-result",
        )
        await _upload_and_publish_result(
            http,
            doctor["access_token"],
            payable_order,
            patient["user_id"],
            doctor["user_id"],
            "metabolic-result",
        )

        await wait_for_notification(
            http,
            NOTIFICATION_URL,
            patient["access_token"],
            "lab_order.all_results_ready",
            "All Lab Results Ready",
            timeout=EVENT_TIMEOUT,
        )

        final_readiness = await poll_until(
            fn=lambda: http.get(
                f"{EMR_URL}/lab-orders/{appointment['id']}/readiness",
                headers={"Authorization": f"Bearer {doctor['access_token']}"},
            ),
            check=lambda response: response.status_code == 200 and response.json()["all_ready"] is True,
            timeout_seconds=EVENT_TIMEOUT,
            label="final lab readiness",
        )
        final_payload = final_readiness.json()
        assert final_payload["total_orders"] == 3
        assert final_payload["completed_results"] == 3
        assert final_payload["all_ready"] is True