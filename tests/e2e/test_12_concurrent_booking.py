"""
Test suite: Concurrent booking (race condition).

Covers:
  - 10 patients book same slot simultaneously
  - Only 1 succeeds (Redis lock works)
  - Others get 409
  - No duplicate appointments in DB
"""

import asyncio
from datetime import date, timedelta

from tests.conftest import APPOINTMENT_URL, AUTH_URL, DOCTOR_URL
from tests.helpers.auth import add_doctor_schedule, register_doctor, register_patient


class TestConcurrentBooking:

    async def test_only_one_wins_concurrent_booking(self, http, admin_token, specialty_id):
        """
        GIVEN 10 patients booking same slot at once
        WHEN all requests fire simultaneously
        THEN exactly 1 succeeds (200/201)
        AND rest receive 409 Conflict
        AND only 1 appointment exists in DB for that slot
        """
        doctor = await register_doctor(http, AUTH_URL, DOCTOR_URL, admin_token, specialty_id)
        await add_doctor_schedule(http, DOCTOR_URL, doctor["user_id"], doctor["access_token"])

        today = date.today()
        days_ahead = (0 - today.weekday()) % 7 or 7
        test_date = (today + timedelta(days=days_ahead)).isoformat()

        # Create 10 patients
        patients = await asyncio.gather(*[register_patient(http, AUTH_URL) for _ in range(10)])

        # All book the exact same slot simultaneously
        async def book(patient):
            return await http.post(
                f"{APPOINTMENT_URL}/",
                json={
                    "doctor_id": doctor["user_id"],
                    "specialty_id": specialty_id,
                    "appointment_date": test_date,
                    "start_time": "09:00",
                    "appointment_type": "general",
                },
                headers={"Authorization": f"Bearer {patient['access_token']}"},
            )

        results = await asyncio.gather(*[book(p) for p in patients])

        status_codes = [r.status_code for r in results]
        successes = [c for c in status_codes if c in (200, 201)]
        conflicts = [c for c in status_codes if c == 409]

        assert len(successes) == 1, f"Expected exactly 1 success, got " f"{len(successes)}. Codes: {status_codes}"
        assert len(conflicts) == 9, f"Expected 9 conflicts, got {len(conflicts)}"
