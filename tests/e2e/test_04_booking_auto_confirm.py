"""
Test suite: Booking with auto_confirm=True.

Covers:
  - Payment paid via VNPay IPN
  - Appointment auto-confirmed after payment success
  - Real-time websocket notification is pushed to patient
"""

import asyncio
import base64
import json
import os
from datetime import date, timedelta

from tests.conftest import APPOINTMENT_URL, AUTH_URL, DOCTOR_URL, EVENT_TIMEOUT, NOTIFICATION_URL, PAYMENT_URL
from tests.helpers.auth import add_doctor_schedule, register_doctor, register_patient
from tests.helpers.vnpay_simulator import VNPaySimulator
from tests.helpers.wait import wait_for_appointment_status, wait_for_payment_record
from tests.helpers.ws_client import WsTestClient


class TestBookingAutoConfirm:

    @staticmethod
    def _jwt_user_id(access_token: str) -> str:
        """Extract user_id claim from JWT payload without signature validation (test-only)."""
        try:
            payload_part = access_token.split(".")[1]
            padding = "=" * (-len(payload_part) % 4)
            payload_raw = base64.urlsafe_b64decode(payload_part + padding)
            payload = json.loads(payload_raw.decode("utf-8"))
            return str(payload.get("user_id") or "")
        except Exception:
            return ""

    @staticmethod
    async def _wait_for_notification_api_event(http, patient_token: str, expected_event_types: set[str], timeout: int):
        """Poll notifications API until one of the expected events is present."""
        headers = {"Authorization": f"Bearer {patient_token}"}
        for _ in range(int(timeout * 2)):
            resp = await http.get(f"{NOTIFICATION_URL}/notifications/me", headers=headers)
            if resp.status_code == 200:
                body = resp.json() or {}
                notifications = body.get("notifications", []) or []
                for n in notifications:
                    if (n or {}).get("event_type") in expected_event_types:
                        return n
            await asyncio.sleep(0.5)
        return None

    async def test_full_auto_confirm_flow(self, http, admin_token, specialty_id):
        """
        GIVEN doctor has auto_confirm=True
        WHEN patient books and pays successfully (IPN=00)
        THEN appointment becomes CONFIRMED automatically
        AND patient receives realtime websocket notification
        """
        patient = await register_patient(http, AUTH_URL)
        doctor = await register_doctor(http, AUTH_URL, DOCTOR_URL, admin_token, specialty_id)
        await add_doctor_schedule(http, DOCTOR_URL, doctor["user_id"], doctor["access_token"])

        # Keep this deterministic even if default config changes.
        auto_confirm_resp = await http.put(
            f"{DOCTOR_URL}/me/auto-confirm",
            json={"auto_confirm": True, "confirmation_timeout_minutes": 15},
            headers={"Authorization": f"Bearer {doctor['access_token']}"},
        )
        assert auto_confirm_resp.status_code == 200, auto_confirm_resp.text

        today = date.today()
        days_ahead = (0 - today.weekday()) % 7 or 7
        test_date = (today + timedelta(days=days_ahead)).isoformat()

        # Shared AsyncClient keeps cookies across helper logins; clear to avoid role/user leakage.
        http.cookies.clear()
        patient_headers = {"Authorization": f"Bearer {patient['access_token']}"}

        patient_ws_user_id = self._jwt_user_id(patient["access_token"]) or patient["user_id"]

        async with WsTestClient(NOTIFICATION_URL, patient_ws_user_id) as ws:
            # Book appointment.
            book_resp = await http.post(
                f"{APPOINTMENT_URL}/",
                json={
                    "doctor_id": doctor["user_id"],
                    "specialty_id": specialty_id,
                    "appointment_date": test_date,
                    "start_time": "09:00",
                    "appointment_type": "general",
                },
                headers=patient_headers,
            )
            assert book_resp.status_code in (200, 201), book_resp.text
            appointment_id = book_resp.json()["id"]
            assert book_resp.json()["status"] == "pending_payment"

            # Wait payment record created by async consumer.
            payment = await wait_for_payment_record(
                http=http,
                payment_url=PAYMENT_URL,
                appointment_id=appointment_id,
                token=patient["access_token"],
                timeout=EVENT_TIMEOUT,
            )

            # Simulate successful VNPay IPN.
            vnpay = VNPaySimulator(os.getenv("VNPAY_HASH_SECRET"), PAYMENT_URL)
            ipn_result = await vnpay.simulate_payment(
                http=http,
                txn_ref=payment["vnpay_txn_ref"],
                amount=payment["amount"],
                success=True,
            )
            assert ipn_result.get("RspCode") == "00", ipn_result

            # Appointment should be confirmed automatically after payment.paid.
            confirmed = await wait_for_appointment_status(
                http=http,
                appointment_url=APPOINTMENT_URL,
                appointment_id=appointment_id,
                expected_status="confirmed",
                token=patient["access_token"],
                timeout=EVENT_TIMEOUT,
            )
            assert confirmed["status"] == "confirmed"

            expected_events = {"appointment.confirmed", "appointment.auto_confirmed", "payment.paid"}

            # Ensure notification has been persisted first (event pipeline completed).
            persisted_notification = await self._wait_for_notification_api_event(
                http=http,
                patient_token=patient["access_token"],
                expected_event_types=expected_events,
                timeout=EVENT_TIMEOUT,
            )
            assert persisted_notification is not None, "Expected notification persisted for auto-confirm flow"

            # Realtime notification should be delivered via websocket.
            realtime_msg = None
            for _ in range(int(EVENT_TIMEOUT * 2)):
                candidates = [
                    m
                    for m in ws.all_messages("notification.new")
                    if (m.get("data") or {}).get("event_type") in expected_events
                ]
                if candidates:
                    realtime_msg = candidates[0]
                    break
                await asyncio.sleep(0.5)

            # In CI/docker setups, WS can occasionally disconnect; reconnect once to flush pending payloads.
            if realtime_msg is None:
                async with WsTestClient(NOTIFICATION_URL, patient_ws_user_id) as ws_retry:
                    for _ in range(int(EVENT_TIMEOUT * 2)):
                        candidates = [
                            m
                            for m in ws_retry.all_messages("notification.new")
                            if (m.get("data") or {}).get("event_type") in expected_events
                        ]
                        if candidates:
                            realtime_msg = candidates[0]
                            break
                        await asyncio.sleep(0.5)

            assert realtime_msg is not None, (
                "Expected websocket notification.new for auto-confirm flow; "
                f"persisted={persisted_notification}, initial_ws={ws.messages}"
            )

    async def test_payment_success_stays_pending_when_auto_confirm_disabled(self, http, admin_token, specialty_id):
        """
        GIVEN doctor has auto_confirm=False
        WHEN patient books and pays successfully (IPN=00)
        THEN appointment remains PENDING (requires manual doctor confirmation)
        """
        patient = await register_patient(http, AUTH_URL)
        doctor = await register_doctor(http, AUTH_URL, DOCTOR_URL, admin_token, specialty_id)
        await add_doctor_schedule(http, DOCTOR_URL, doctor["user_id"], doctor["access_token"])

        auto_confirm_resp = await http.put(
            f"{DOCTOR_URL}/me/auto-confirm",
            json={"auto_confirm": False, "confirmation_timeout_minutes": 15},
            headers={"Authorization": f"Bearer {doctor['access_token']}"},
        )
        assert auto_confirm_resp.status_code == 200, auto_confirm_resp.text

        today = date.today()
        days_ahead = (0 - today.weekday()) % 7 or 7
        test_date = (today + timedelta(days=days_ahead)).isoformat()

        # Shared AsyncClient keeps cookies across helper logins; clear to avoid role/user leakage.
        http.cookies.clear()
        patient_headers = {"Authorization": f"Bearer {patient['access_token']}"}

        book_resp = await http.post(
            f"{APPOINTMENT_URL}/",
            json={
                "doctor_id": doctor["user_id"],
                "specialty_id": specialty_id,
                "appointment_date": test_date,
                "start_time": "10:00",
                "appointment_type": "general",
            },
            headers=patient_headers,
        )
        assert book_resp.status_code in (200, 201), book_resp.text
        appointment_id = book_resp.json()["id"]
        assert book_resp.json()["status"] == "pending_payment"

        payment = await wait_for_payment_record(
            http=http,
            payment_url=PAYMENT_URL,
            appointment_id=appointment_id,
            token=patient["access_token"],
            timeout=EVENT_TIMEOUT,
        )

        vnpay = VNPaySimulator(os.getenv("VNPAY_HASH_SECRET"), PAYMENT_URL)
        ipn_result = await vnpay.simulate_payment(
            http=http,
            txn_ref=payment["vnpay_txn_ref"],
            amount=payment["amount"],
            success=True,
        )
        assert ipn_result.get("RspCode") == "00", ipn_result

        pending = await wait_for_appointment_status(
            http=http,
            appointment_url=APPOINTMENT_URL,
            appointment_id=appointment_id,
            expected_status="pending",
            token=patient["access_token"],
            timeout=EVENT_TIMEOUT,
        )
        assert pending["status"] == "pending"
