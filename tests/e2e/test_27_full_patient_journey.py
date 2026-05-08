"""
E2E test suite: Full Patient Journey.

Covers the complete end-to-end clinical flow in one integrated test:
  1.  Patient books appointment + payment (auto-confirm)
  2.  Doctor starts the appointment
  3.  Doctor creates a lab order
  4.  Doctor uploads a MANUAL lab result  (→ DOCTOR_REVIEW immediately, no Celery wait)
  5.  Doctor verifies and publishes the result
  6.  Patient reads the published lab result
  7.  Patient asks the AI about the result  (POST /ai/lab-chat, SSE streaming)
  8.  Patient continues the conversation with the same session  (session continuity)
  9.  Doctor writes a clinical note
  10. Doctor marks the appointment COMPLETED
  11. Patient rates the doctor (5 stars)
  12. Rating appears in the doctor's public profile
"""

import os
from datetime import date, timedelta

import pytest

from tests.conftest import APPOINTMENT_URL, AUTH_URL, DOCTOR_URL, EVENT_TIMEOUT, PAYMENT_URL
from tests.helpers.auth import add_doctor_schedule, register_doctor, register_patient
from tests.helpers.vnpay_simulator import VNPaySimulator
from tests.helpers.wait import poll_until, wait_for_appointment_status, wait_for_payment_record

EMR_URL = os.getenv("EMR_URL", "http://localhost:8000")
CLINICAL_URL = os.getenv("CLINICAL_URL", "http://localhost:8000/clinical")
AI_URL = os.getenv("AI_URL", "http://localhost:8000/ai")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_sse(body: str) -> tuple[str | None, list[str]]:
    """Parse a full SSE response body.

    Returns:
        session_id  – extracted from ``event: session_id`` block, or None.
        text_chunks – all plain ``data:`` lines (excluding [DONE]).
    """
    session_id: str | None = None
    text_chunks: list[str] = []

    for block in body.split("\n\n"):
        lines = block.strip().split("\n")
        has_session_event = any("event: session_id" in ln for ln in lines)
        data_lines = [ln[6:] for ln in lines if ln.startswith("data: ")]

        if has_session_event and data_lines:
            session_id = data_lines[0].strip()
        elif data_lines:
            for d in data_lines:
                stripped = d.strip()
                if stripped and stripped != "[DONE]":
                    text_chunks.append(stripped)

    return session_id, text_chunks


# ---------------------------------------------------------------------------
# Test suite
# ---------------------------------------------------------------------------

class TestFullPatientJourney:
    """Single integrated E2E test covering the full patient journey."""

    @pytest.mark.e2e
    async def test_full_journey_booking_to_rating(self, http, admin_token, specialty_id):
        """
        Book → Pay → Doctor Start → Lab Order → Manual Lab Result →
        Doctor Verify & Publish → Patient Read Result →
        Patient Chat AI About Result → Clinical Note →
        Complete Appointment → Rate Doctor → Verify Rating
        """
        # ── Setup: register patient and doctor ───────────────────────────────
        patient = await register_patient(http, AUTH_URL)
        doctor = await register_doctor(http, AUTH_URL, DOCTOR_URL, admin_token, specialty_id)
        await add_doctor_schedule(http, DOCTOR_URL, doctor["user_id"], doctor["access_token"])

        # Enable auto-confirm so the appointment moves to CONFIRMED after payment.
        auto_resp = await http.put(
            f"{DOCTOR_URL}/me/auto-confirm",
            json={"auto_confirm": True, "confirmation_timeout_minutes": 60},
            headers={"Authorization": f"Bearer {doctor['access_token']}"},
        )
        assert auto_resp.status_code == 200, f"auto-confirm setup failed: {auto_resp.text}"

        patient_hdrs = {"Authorization": f"Bearer {patient['access_token']}"}
        doctor_hdrs = {"Authorization": f"Bearer {doctor['access_token']}"}

        # Book on a weekday 7 days from now.
        appointment_date = str(date.today() + timedelta(days=7))

        # ── Step 1: Book appointment ─────────────────────────────────────────
        book_resp = await http.post(
            f"{APPOINTMENT_URL}/",
            json={
                "doctor_id": doctor["user_id"],
                "specialty_id": specialty_id,
                "appointment_date": appointment_date,
                "start_time": "10:00",
                "appointment_type": "general",
            },
            headers=patient_hdrs,
        )
        assert book_resp.status_code in (200, 201), f"Booking failed: {book_resp.text}"
        appointment_id = book_resp.json()["id"]

        # ── Step 2: Simulate VNPay payment ───────────────────────────────────
        payment = await wait_for_payment_record(
            http=http,
            payment_url=PAYMENT_URL,
            appointment_id=appointment_id,
            token=patient["access_token"],
            timeout=EVENT_TIMEOUT,
        )
        vnpay = VNPaySimulator(os.getenv("VNPAY_HASH_SECRET"), PAYMENT_URL)
        ipn = await vnpay.simulate_payment(
            http, payment["vnpay_txn_ref"], payment["amount"], success=True
        )
        assert ipn.get("RspCode") == "00", f"VNPay IPN failed: {ipn}"

        appt = await wait_for_appointment_status(
            http, APPOINTMENT_URL, appointment_id, "CONFIRMED",
            patient["access_token"], timeout=EVENT_TIMEOUT,
        )
        assert appt["status"] == "CONFIRMED"

        # ── Step 3: Doctor starts the appointment ────────────────────────────
        start_resp = await http.put(
            f"{APPOINTMENT_URL}/{appointment_id}/start",
            headers=doctor_hdrs,
        )
        assert start_resp.status_code == 200, f"Start appointment failed: {start_resp.text}"
        assert start_resp.json()["status"] == "IN_PROGRESS"

        # ── Step 4: Doctor creates a lab order ───────────────────────────────
        order_resp = await http.post(
            f"{EMR_URL}/lab-orders",
            headers=doctor_hdrs,
            json={
                "patient_id": patient["user_id"],
                "doctor_id": doctor["user_id"],
                "appointment_id": appointment_id,
                "test_name": "Complete Blood Count",
                "test_type": "blood_panel",
                "priority": "routine",
            },
        )
        assert order_resp.status_code == 201, f"Lab order failed: {order_resp.text}"
        order_id = order_resp.json()["id"]

        # ── Step 5: Doctor uploads MANUAL lab result (no Celery AI wait) ─────
        # file_type="manual" → status goes directly to DOCTOR_REVIEW.
        result_resp = await http.post(
            f"{EMR_URL}/lab-results",
            headers=doctor_hdrs,
            json={
                "order_id": order_id,
                "patient_id": patient["user_id"],
                "doctor_id": doctor["user_id"],
                "file_type": "manual",
                "manual_entries": [
                    {
                        "test_name": "WBC",
                        "value": "6.8",
                        "unit": "K/uL",
                        "reference_range": "4.5-11.0",
                    },
                    {
                        "test_name": "Hemoglobin",
                        "value": "11.2",
                        "unit": "g/dL",
                        "reference_range": "12.0-16.0",
                    },
                    {
                        "test_name": "Platelets",
                        "value": "245",
                        "unit": "K/uL",
                        "reference_range": "150-400",
                    },
                ],
                "notes": "Manual entry from physical lab report",
            },
        )
        assert result_resp.status_code == 201, f"Lab result upload failed: {result_resp.text}"
        result_id = result_resp.json()["id"]
        assert result_resp.json()["status"] == "DOCTOR_REVIEW", (
            "Manual entry should move directly to DOCTOR_REVIEW"
        )

        # ── Step 6: Doctor verifies and publishes the result ─────────────────
        verify_resp = await http.patch(
            f"{EMR_URL}/lab-results/{result_id}/verify",
            headers=doctor_hdrs,
            json={
                "doctor_notes": "Hemoglobin slightly low — monitor and recommend iron-rich diet.",
                "published_text": (
                    "CBC reviewed. Hemoglobin slightly below normal range. "
                    "WBC and Platelets are normal. Follow-up in 4 weeks recommended."
                ),
            },
        )
        assert verify_resp.status_code == 200, f"Verify failed: {verify_resp.text}"
        assert verify_resp.json()["status"] == "PUBLISHED"

        # ── Step 7: Patient reads the published lab result ───────────────────
        get_result_resp = await http.get(
            f"{EMR_URL}/lab-results/{result_id}",
            headers=patient_hdrs,
        )
        assert get_result_resp.status_code == 200, f"Get result failed: {get_result_resp.text}"
        result_data = get_result_resp.json()
        assert result_data["status"] == "PUBLISHED"
        assert result_data.get("published_text"), "published_text should not be empty"

        # ── Step 8: Patient asks the AI about the result (lab-chat SSE) ──────
        ai_health = await http.get(f"{AI_URL}/health")
        if ai_health.status_code != 200:
            pytest.skip("AI Service not reachable — skipping lab-chat steps")

        chat_resp = await http.post(
            f"{AI_URL}/lab-chat",
            headers=patient_hdrs,
            json={
                "question": "Hemoglobin của tôi hơi thấp có nghĩa là gì và tôi có cần lo lắng không?",
                "patient_id": patient["user_id"],
                "department": "hematology",
            },
        )
        assert chat_resp.status_code == 200, f"lab-chat failed: {chat_resp.text[:300]}"

        session_id, text_chunks = _parse_sse(chat_resp.text)
        assert session_id is not None, (
            f"Expected 'event: session_id' in SSE stream. Body snippet: {chat_resp.text[:500]}"
        )
        assert len(text_chunks) > 0, (
            f"Expected non-empty AI response. Body snippet: {chat_resp.text[:400]}"
        )

        # ── Step 9: Patient continues the conversation (session continuity) ──
        followup_resp = await http.post(
            f"{AI_URL}/lab-chat",
            headers=patient_hdrs,
            json={
                "question": "Tôi nên ăn gì để cải thiện chỉ số hemoglobin?",
                "patient_id": patient["user_id"],
                "department": "hematology",
                "session_id": session_id,
            },
        )
        assert followup_resp.status_code == 200, (
            f"lab-chat follow-up failed: {followup_resp.text[:300]}"
        )
        _, followup_chunks = _parse_sse(followup_resp.text)
        assert len(followup_chunks) > 0, "Expected non-empty AI follow-up response"

        # ── Step 10: Doctor writes a clinical note ───────────────────────────
        note_resp = await http.post(
            f"{CLINICAL_URL}/patients/{patient['user_id']}/notes",
            headers=doctor_hdrs,
            json={
                "patient_id": patient["user_id"],
                "doctor_id": doctor["user_id"],
                "content": (
                    "Patient presents with mild hemoglobin deficiency (11.2 g/dL). "
                    "CBC otherwise normal. Dietary advice given. Follow-up in 4 weeks."
                ),
                "note_type": "soap",
                "is_ai_generated": False,
            },
        )
        assert note_resp.status_code == 201, f"Clinical note failed: {note_resp.text}"

        # ── Step 11: Doctor completes the appointment ────────────────────────
        complete_resp = await http.put(
            f"{APPOINTMENT_URL}/{appointment_id}/complete",
            headers=doctor_hdrs,
        )
        assert complete_resp.status_code == 200, f"Complete appointment failed: {complete_resp.text}"
        assert complete_resp.json()["status"] == "COMPLETED"

        # ── Step 12: Patient rates the doctor (5 stars) ──────────────────────
        rating_resp = await http.post(
            f"{DOCTOR_URL}/{doctor['user_id']}/ratings",
            params={
                "rating": 5,
                "appointment_id": appointment_id,
                "comment": "Bác sĩ rất tận tâm, giải thích kết quả xét nghiệm rõ ràng.",
            },
            headers=patient_hdrs,
        )
        assert rating_resp.status_code == 200, f"Rating submission failed: {rating_resp.text}"
        rating_id = rating_resp.json().get("rating_id")
        assert rating_id is not None, "Expected rating_id in response"

        # ── Step 13: Verify rating appears in the doctor's public profile ─────
        ratings_resp = await poll_until(
            fn=lambda: http.get(
                f"{DOCTOR_URL}/{doctor['user_id']}/ratings",
                headers=patient_hdrs,
            ),
            check=lambda r: r.status_code == 200 and any(
                item.get("rating") == 5
                for item in (r.json().get("ratings") or [])
            ),
            timeout_seconds=10,
            label="rating=5 appears in doctor profile",
        )
        all_ratings = ratings_resp.json().get("ratings") or []
        assert any(item.get("rating") == 5 for item in all_ratings), (
            f"Rating 5 not found in doctor profile. Got: {all_ratings}"
        )
