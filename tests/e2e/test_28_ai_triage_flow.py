"""
E2E test suite: AI Triage Session Flow.

Covers the pre-consultation AI triage flow:
  1. Patient sends symptoms → AI replies via SSE → session_id captured
  2. Patient retrieves their triage session via GET
  3. Patient lists their own sessions (session appears in list)
  4. Doctor lists all triage sessions (session visible)
  5. Doctor confirms the triage → status transitions to doctor_confirmed
  6. Confirmed session reflects doctor_id and doctor_notes
"""

import os

import pytest

from tests.conftest import AUTH_URL, DOCTOR_URL
from tests.helpers.auth import register_doctor, register_patient

AI_URL = os.getenv("AI_URL", "http://localhost:8000/ai")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_sse_session_id(body: str) -> str | None:
    """Extract session_id value from ``event: session_id`` SSE block."""
    for block in body.split("\n\n"):
        lines = block.strip().split("\n")
        has_session_event = any("event: session_id" in ln for ln in lines)
        data_lines = [ln[6:] for ln in lines if ln.startswith("data: ")]
        if has_session_event and data_lines:
            return data_lines[0].strip()
    return None


def _parse_sse_chunks(body: str) -> list[str]:
    """Extract all plain-text data chunks from SSE body (excluding [DONE])."""
    chunks = []
    for ln in body.split("\n"):
        if ln.startswith("data: "):
            text = ln[6:].strip()
            if text and text != "[DONE]":
                chunks.append(text)
    return chunks


# ---------------------------------------------------------------------------
# Test suite
# ---------------------------------------------------------------------------

@pytest.mark.e2e
class TestAITriageFlow:
    """AI triage session lifecycle: patient → AI → doctor review → confirm."""

    async def test_ai_triage_session_full_flow(self, http, admin_token, specialty_id):
        """
        Patient sends symptoms → SSE stream → session created →
        Doctor lists + confirms session → status = doctor_confirmed.
        """
        # ── Setup ─────────────────────────────────────────────────────────────
        patient = await register_patient(http, AUTH_URL)
        doctor = await register_doctor(http, AUTH_URL, DOCTOR_URL, admin_token, specialty_id)

        patient_hdrs = {"Authorization": f"Bearer {patient['access_token']}"}
        doctor_hdrs = {"Authorization": f"Bearer {doctor['access_token']}"}

        # ── Pre-check: AI service must be reachable ────────────────────────────
        health = await http.get(f"{AI_URL}/health")
        if health.status_code != 200:
            pytest.skip("AI Service not reachable — skipping triage flow test")

        # ── Step 1: Patient sends symptoms → SSE stream ───────────────────────
        symptom_resp = await http.post(
            f"{AI_URL}/symptom-check",
            headers=patient_hdrs,
            json={
                "patient_id": patient["user_id"],
                "symptoms": (
                    "Ho khan kéo dài hơn 2 tuần, khó thở khi gắng sức, "
                    "thỉnh thoảng đau ngực trái."
                ),
            },
        )
        assert symptom_resp.status_code == 200, (
            f"symptom-check failed: {symptom_resp.text[:300]}"
        )

        # Every /symptom-check response must start with event: session_id.
        session_id = _parse_sse_session_id(symptom_resp.text)
        assert session_id is not None, (
            f"Expected 'event: session_id' in SSE stream. "
            f"Body snippet: {symptom_resp.text[:500]}"
        )

        # AI must produce at least one text chunk.
        chunks = _parse_sse_chunks(symptom_resp.text)
        assert len(chunks) > 0, (
            f"Expected non-empty AI response. Body snippet: {symptom_resp.text[:400]}"
        )

        # ── Step 2: Patient retrieves their triage session ─────────────────────
        get_session_resp = await http.get(
            f"{AI_URL}/triage-sessions/{session_id}",
            headers=patient_hdrs,
        )
        assert get_session_resp.status_code == 200, (
            f"GET triage session failed: {get_session_resp.text}"
        )
        session_data = get_session_resp.json()
        assert session_data["id"] == session_id
        assert session_data["patient_id"] == patient["user_id"]
        assert len(session_data.get("messages", [])) > 0, (
            "Session should contain at least one message turn"
        )

        # ── Step 3: Patient lists their own sessions ───────────────────────────
        patient_list_resp = await http.get(
            f"{AI_URL}/triage-sessions",
            headers=patient_hdrs,
        )
        assert patient_list_resp.status_code == 200
        patient_sessions = patient_list_resp.json().get("sessions") or []
        patient_session_ids = [s["id"] for s in patient_sessions]
        assert session_id in patient_session_ids, (
            f"Session {session_id} not found in patient's own session list. "
            f"Got: {patient_session_ids}"
        )

        # ── Step 4: Doctor lists all triage sessions ───────────────────────────
        doctor_list_resp = await http.get(
            f"{AI_URL}/triage-sessions",
            headers=doctor_hdrs,
        )
        assert doctor_list_resp.status_code == 200
        all_sessions = doctor_list_resp.json().get("sessions") or []
        all_session_ids = [s["id"] for s in all_sessions]
        assert session_id in all_session_ids, (
            f"Session {session_id} not visible in doctor's session list. "
            f"Got: {all_session_ids}"
        )

        # ── Step 5: Doctor confirms the triage session ─────────────────────────
        confirm_resp = await http.post(
            f"{AI_URL}/triage-sessions/{session_id}/confirm",
            headers=doctor_hdrs,
            json={
                "notes": (
                    "Triệu chứng phù hợp với bệnh lý hô hấp. "
                    "Chuyển khoa Hô hấp để khám và điều trị."
                ),
            },
        )
        assert confirm_resp.status_code == 200, (
            f"Confirm triage session failed: {confirm_resp.text}"
        )
        confirmed = confirm_resp.json()
        assert confirmed["status"] == "doctor_confirmed", (
            f"Expected status=doctor_confirmed, got: {confirmed['status']}"
        )
        assert confirmed["doctor_id"] == doctor["user_id"], (
            "doctor_id on confirmed session must match the confirming doctor"
        )

        # ── Step 6: Verify final session state via GET ─────────────────────────
        final_resp = await http.get(
            f"{AI_URL}/triage-sessions/{session_id}",
            headers=patient_hdrs,
        )
        assert final_resp.status_code == 200
        final_data = final_resp.json()
        assert final_data["status"] == "doctor_confirmed", (
            f"Expected final status=doctor_confirmed, got: {final_data['status']}"
        )
