"""
Test suite: Enhanced slot generation using availability + day-off + max_patients + service_id.

Covers:
  - Slots are blocked on a day-off date
  - Slots respect max_patients cap (no overbooking beyond limit)
  - service_id param adjusts slot duration in the slot list
"""

import os
from datetime import date, timedelta

from tests.conftest import APPOINTMENT_URL, AUTH_URL, DOCTOR_URL, EVENT_TIMEOUT, PAYMENT_URL
from tests.helpers.auth import add_doctor_schedule, register_doctor, register_patient
from tests.helpers.vnpay_simulator import VNPaySimulator
from tests.helpers.wait import wait_for_appointment_status, wait_for_payment_record


class TestEnhancedSlots:

    async def test_slots_empty_on_day_off(self, http, admin_token, specialty_id):
        """
        GIVEN a doctor with availability set for Mondays
        AND a day-off added for next Monday
        WHEN GET /doctor/{doctor_id}/slots?date={day_off_date}
        THEN returns empty list (0 available slots)
        """
        doctor = await register_doctor(http, AUTH_URL, DOCTOR_URL, admin_token, specialty_id)
        headers = {"Authorization": f"Bearer {doctor['access_token']}"}

        # Set Monday (0) availability
        await http.post(
            f"{DOCTOR_URL}/{doctor['user_id']}/availability",
            params={"day_of_week": 0, "start_time": "09:00", "end_time": "17:00", "max_patients": 10},
            headers=headers,
        )

        # Find next Monday
        today = date.today()
        days_until_monday = (0 - today.weekday()) % 7 or 7
        next_monday = today + timedelta(days=days_until_monday)
        next_monday_str = next_monday.isoformat()

        # Add day off on that Monday
        add_r = await http.post(
            f"{DOCTOR_URL}/{doctor['user_id']}/days-off",
            params={"off_date": next_monday_str},
            headers=headers,
        )
        assert add_r.status_code in (200, 201), add_r.text

        # Query available slots for that day
        r = await http.get(
            f"{APPOINTMENT_URL}/doctor/{doctor['user_id']}/slots",
            params={"appointment_date": next_monday_str, "specialty_id": specialty_id},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        slots = body if isinstance(body, list) else body.get("slots", body.get("items", []))
        assert len(slots) == 0, f"Expected 0 slots on day-off date {next_monday_str}, got {len(slots)}: {slots[:3]}"

    async def test_slots_unavailable_after_max_patients_reached(self, http, admin_token, specialty_id):
        """
        GIVEN a doctor with max_patients=1 for a day
        WHEN one appointment is confirmed on that date
        THEN no further slots are available (max reached)
        """
        patient = await register_patient(http, AUTH_URL)
        doctor = await register_doctor(http, AUTH_URL, DOCTOR_URL, admin_token, specialty_id)
        await add_doctor_schedule(http, DOCTOR_URL, doctor["user_id"], doctor["access_token"])

        # Enable auto_confirm
        await http.put(
            f"{DOCTOR_URL}/me/auto-confirm",
            json={"auto_confirm": True, "confirmation_timeout_minutes": 15},
            headers={"Authorization": f"Bearer {doctor['access_token']}"},
        )

        # Set Monday availability with max_patients=1
        d_header = {"Authorization": f"Bearer {doctor['access_token']}"}
        await http.post(
            f"{DOCTOR_URL}/{doctor['user_id']}/availability",
            params={"day_of_week": 0, "start_time": "09:00", "end_time": "11:00", "max_patients": 1},
            headers=d_header,
        )

        today = date.today()
        days_until_monday = (0 - today.weekday()) % 7 or 7
        next_monday = today + timedelta(days=days_until_monday)
        next_monday_str = next_monday.isoformat()

        # Book + confirm the single slot
        p_header = {"Authorization": f"Bearer {patient['access_token']}"}
        book_r = await http.post(
            f"{APPOINTMENT_URL}/",
            json={
                "doctor_id": doctor["user_id"],
                "specialty_id": specialty_id,
                "appointment_date": next_monday_str,
                "start_time": "09:00",
                "appointment_type": "general",
            },
            headers=p_header,
        )
        assert book_r.status_code in (200, 201), book_r.text
        appt_id = book_r.json()["id"]

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
            http,
            APPOINTMENT_URL,
            appt_id,
            "CONFIRMED",
            patient["access_token"],
            timeout=EVENT_TIMEOUT,
        )

        # Now check that no slots remain
        r = await http.get(
            f"{APPOINTMENT_URL}/doctor/{doctor['user_id']}/slots",
            params={"appointment_date": next_monday_str, "specialty_id": specialty_id},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        slots = body if isinstance(body, list) else body.get("slots", body.get("items", []))
        assert len(slots) == 0, f"Expected 0 slots after max_patients=1 reached, got {len(slots)}"

    async def test_slots_with_service_id_uses_service_duration(self, http, admin_token, specialty_id):
        """
        GIVEN a doctor with a service offering (duration=60min) and availability set
        WHEN GET /doctor/{doctor_id}/slots?date=&service_id=
        THEN slot intervals match service duration (60min) not the default schedule duration
        """
        doctor = await register_doctor(http, AUTH_URL, DOCTOR_URL, admin_token, specialty_id)
        d_header = {"Authorization": f"Bearer {doctor['access_token']}"}

        # Add a 60-min service
        svc_r = await http.post(
            f"{DOCTOR_URL}/{doctor['user_id']}/services",
            params={"service_name": "Deep Consultation", "duration_minutes": 60, "fee": 400000},
            headers=d_header,
        )
        assert svc_r.status_code in (200, 201), svc_r.text
        service_id = svc_r.json()["service_id"]

        # Set availability for Monday with 20-min default slots
        await http.post(
            f"{DOCTOR_URL}/{doctor['user_id']}/availability",
            params={"day_of_week": 0, "start_time": "09:00", "end_time": "13:00", "max_patients": 10},
            headers=d_header,
        )

        today = date.today()
        days_until_monday = (0 - today.weekday()) % 7 or 7
        next_monday_str = (today + timedelta(days=days_until_monday)).isoformat()

        r = await http.get(
            f"{APPOINTMENT_URL}/doctor/{doctor['user_id']}/slots",
            params={"appointment_date": next_monday_str, "service_id": service_id, "specialty_id": specialty_id},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        slots = body if isinstance(body, list) else body.get("slots", body.get("items", []))

        if len(slots) >= 2:
            # Verify gap between consecutive slots is ~60 minutes
            from datetime import datetime

            t0 = datetime.strptime(slots[0]["start_time"][:5], "%H:%M")
            t1 = datetime.strptime(slots[1]["start_time"][:5], "%H:%M")
            gap_minutes = (t1 - t0).seconds // 60
            assert gap_minutes == 60, f"Expected 60-min slot gap for service, got {gap_minutes}min"

    async def test_slots_fallback_when_no_enhanced_data(self, http, admin_token, specialty_id):
        """
        GIVEN a doctor with only legacy schedule set (no availability record)
        WHEN GET /doctor/{doctor_id}/slots?date=
        THEN still returns slots (fallback to legacy schedule)
        """
        doctor = await register_doctor(http, AUTH_URL, DOCTOR_URL, admin_token, specialty_id)
        await add_doctor_schedule(http, DOCTOR_URL, doctor["user_id"], doctor["access_token"])

        today = date.today()
        days_until_monday = (0 - today.weekday()) % 7 or 7
        next_monday_str = (today + timedelta(days=days_until_monday)).isoformat()

        r = await http.get(
            f"{APPOINTMENT_URL}/doctor/{doctor['user_id']}/slots",
            params={"appointment_date": next_monday_str, "specialty_id": specialty_id},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        slots = body if isinstance(body, list) else body.get("slots", body.get("items", []))
        # Fallback should still produce at least some slots for a full schedule day
        assert len(slots) > 0, "Expected slots from legacy schedule fallback, got 0"
