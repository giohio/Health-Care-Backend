"""
E2E test: full booking flow via HTTP endpoint inside the container.
Run: docker exec ai_service python /app/scripts/test_e2e_booking.py
"""
import asyncio
import json
import sys
sys.path.insert(0, '/app')
import httpx

BASE = "http://localhost:8000"
PATIENT_ID = "675cf94c-463b-438e-ab9f-d4e09f069e4e"
HEADERS = {
    "x-user-id": PATIENT_ID,
    "x-user-role": "patient",
    "Content-Type": "application/json",
}


def sse_parse(raw: str) -> dict:
    result = {"text": "", "session_id": None, "turn_type": None, "specialties": None, "appointment_created": None}
    lines = raw.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("event: session_id") and i + 1 < len(lines):
            result["session_id"] = lines[i + 1].replace("data: ", "")
            i += 2
            continue
        if line.startswith("event: turn_type") and i + 1 < len(lines):
            result["turn_type"] = lines[i + 1].replace("data: ", "")
            i += 2
            continue
        if line.startswith("event: specialties") and i + 1 < len(lines):
            result["specialties"] = lines[i + 1].replace("data: ", "")
            i += 2
            continue
        if line.startswith("event: appointment_created") and i + 1 < len(lines):
            result["appointment_created"] = lines[i + 1].replace("data: ", "")
            i += 2
            continue
        if line.startswith("data: ") and line != "data: [DONE]":
            result["text"] += line[6:]
        i += 1
    return result


async def call(symptoms: str, session_id: str | None = None) -> tuple[dict, str]:
    body: dict = {"patient_id": PATIENT_ID, "symptoms": symptoms}
    if session_id:
        body["session_id"] = session_id
    async with httpx.AsyncClient(timeout=90) as c:
        resp = await c.post(f"{BASE}/symptom-check", json=body, headers=HEADERS)
        parsed = sse_parse(resp.text)
        return parsed, resp.text


async def main():
    print("=== E2E BOOKING FLOW TEST ===\n")

    # ── Turn 1 ────────────────────────────────────────────────────────────
    msg1 = "I have a persistent headache and dizziness for over 1 week"
    print(f"[TURN 1] Patient: {msg1!r}")
    r, raw = await call(msg1)
    session_id = r["session_id"]
    print(f"  session_id : {session_id}")
    print(f"  turn_type  : {r['turn_type']}")
    print(f"  response   : {r['text'][:250]}")
    print()

    # ── If still questions, answer them ───────────────────────────────────
    turn_n = 2
    while r["turn_type"] == "question" and turn_n <= 4:
        follow = "dull pressure across whole head, more than 1 week, also have dizziness, no fever"
        print(f"[TURN {turn_n}] Patient: {follow!r}")
        r, raw = await call(follow, session_id)
        print(f"  turn_type  : {r['turn_type']}")
        print(f"  specialties: {r['specialties']}")
        print(f"  response   : {r['text'][:300]}")
        print()
        turn_n += 1

    if r["turn_type"] != "recommendation":
        print("FAIL: did not get [R] recommendation after several turns")
        sys.exit(1)

    print("  [R] received. Has booking offer:", "book" in r["text"].lower())
    print()

    # ── Booking turn ──────────────────────────────────────────────────────
    book_msg = "Can u book for me pls"
    print(f"[BOOKING TURN] Patient: {book_msg!r}")
    r, raw = await call(book_msg, session_id)
    print(f"  turn_type  : {r['turn_type']}")
    print(f"  response   : {r['text'][:400]}")
    print()

    slot_indicators = ["opening", "option", "I found", "Tôi tìm", "no available", "lựa chọn"]
    has_slots = any(x in r["text"] for x in slot_indicators)
    if not has_slots:
        print("FAIL: booking bypass did not fire — LLM responded instead")
        print("raw SSE (first 600):", raw[:600])
        sys.exit(1)

    print("  BOOKING BYPASS FIRED — slots shown to patient!")
    print()

    # ── Confirmation turn ─────────────────────────────────────────────────
    confirm_msg = "yes"
    print(f"[CONFIRM TURN] Patient: {confirm_msg!r}")
    r, raw = await call(confirm_msg, session_id)
    print(f"  turn_type          : {r['turn_type']}")
    print(f"  response           : {r['text']}")
    print(f"  appointment_created: {r['appointment_created']}")
    print()

    if r["appointment_created"] or any(x in r["text"] for x in ["confirmed", "Appointment", "Booking ID", "Đã đặt"]):
        print("=== RESULT: SUCCESS — AI booked the appointment end-to-end! ===")
        if r["appointment_created"]:
            print(f"  appointment_created event: {r['appointment_created']}")
            print("  FE should listen for this event and call GET /appointments to refresh.")
    else:
        print("PARTIAL: confirmation turn did not return appointment details")
        print("raw SSE:", raw[:600])


if __name__ == "__main__":
    asyncio.run(main())
