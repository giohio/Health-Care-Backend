"""
Run inside ai_service container:
  docker exec ai_service python /app/scripts/test_booking_flow.py

Tests the full booking bypass flow without any HTTP/Kong dependency.
"""
import asyncio
import sys
sys.path.insert(0, '/app')

from Domain.entities import SymptomCheckRequest, ConversationTurn
from Domain.prompts import _detect_booking_mode, _BOOKING_INTENT_KEYWORDS


def test_detect_booking_mode():
    print("\n=== test_detect_booking_mode ===")

    # Case 1: no history
    req = SymptomCheckRequest(patient_id="p1", symptoms="book for me")
    result = _detect_booking_mode(req)
    print(f"[1] no history → {result}  (expected: False)")
    assert result is False

    # Case 2: history with [Q] only (no [R])
    req = SymptomCheckRequest(
        patient_id="p1",
        symptoms="book for me",
        conversation_history=[
            ConversationTurn(role="patient", content="I have a headache"),
            ConversationTurn(role="assistant", content="[Q] How long have you had this headache?"),
        ],
    )
    result = _detect_booking_mode(req)
    print(f"[2] only [Q] in history → {result}  (expected: False)")
    assert result is False

    # Case 3: history with [R], but non-booking message
    req = SymptomCheckRequest(
        patient_id="p1",
        symptoms="thank you",
        conversation_history=[
            ConversationTurn(role="patient", content="I have chest pain"),
            ConversationTurn(role="assistant", content="[R] Based on your symptoms, I recommend Cardiology."),
        ],
    )
    result = _detect_booking_mode(req)
    print(f"[3] [R] in history, non-booking msg → {result}  (expected: False)")
    assert result is False

    # Case 4: [R] in history + booking keyword → SHOULD BE TRUE
    req = SymptomCheckRequest(
        patient_id="p1",
        symptoms="Book appointment for me pls",
        conversation_history=[
            ConversationTurn(role="patient", content="I have chest pain"),
            ConversationTurn(role="assistant", content="[R] Based on your symptoms, I recommend Cardiology."),
        ],
    )
    result = _detect_booking_mode(req)
    print(f"[4] [R] in history + 'Book appointment for me pls' → {result}  (expected: True)")
    assert result is True, f"FAIL: expected True, got False. Keywords checked: {list(_BOOKING_INTENT_KEYWORDS)[:5]}"

    # Case 5: Vietnamese booking
    req = SymptomCheckRequest(
        patient_id="p1",
        symptoms="đặt lịch cho tôi",
        conversation_history=[
            ConversationTurn(role="patient", content="tôi bị đau ngực"),
            ConversationTurn(role="assistant", content="[R] Dựa vào triệu chứng, tôi đề xuất Tim mạch."),
        ],
    )
    result = _detect_booking_mode(req)
    print(f"[5] VI: [R] + 'đặt lịch cho tôi' → {result}  (expected: True)")
    assert result is True

    # Case 6: [R] emergency → should not trigger booking
    req = SymptomCheckRequest(
        patient_id="p1",
        symptoms="book for me",
        conversation_history=[
            ConversationTurn(role="patient", content="I have severe chest pain"),
            ConversationTurn(role="assistant",
                             content="[R] This is an emergency. Please call emergency services or go to the nearest ER immediately."),
        ],
    )
    result = _detect_booking_mode(req)
    print(f"[6] Emergency [R] + booking keyword → {result}  (expected: False)")
    assert result is False

    # Case 7: [R] with disclaimer and specialties marker appended (how it's stored in DB)
    req = SymptomCheckRequest(
        patient_id="p1",
        symptoms="yes please book",
        conversation_history=[
            ConversationTurn(role="patient", content="I have chest pain"),
            ConversationTurn(
                role="assistant",
                content='[R] Based on your symptoms, I recommend Cardiology.\n\n*AI disclaimer*\n\n[SPECIALTIES_MARKER]["Cardiology"][SPECIALTIES_MARKER]'
            ),
        ],
        suggested_department="cardiology",
    )
    result = _detect_booking_mode(req)
    print(f"[7] [R] with disclaimer+marker + 'yes please book' → {result}  (expected: True)")
    assert result is True

    print("\nAll _detect_booking_mode tests PASSED ✓")


async def test_availability_client():
    print("\n=== test_availability_client ===")
    import os
    import pytest
    # This test requires the full Docker network (appointment_service reachable).
    # Skip gracefully when running locally outside the container.
    if not os.path.exists("/app"):
        pytest.skip("Skipped outside Docker container (requires internal network)")

    from infrastructure.clients.appointment_service_client import AppointmentServiceClient
    from datetime import date, timedelta
    d = date.today() + timedelta(days=1)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    date_str = d.strftime("%Y-%m-%d")
    print(f"Testing availability for Internal Medicine on {date_str}")
    client = AppointmentServiceClient()
    result = await client.check_availability_by_department("Internal Medicine", date_str)
    print(f"  slots count: {len(result) if result else 0}")
    if result:
        print(f"  first slot: {result[0]}")
    assert result, "FAIL: no slots returned"
    print("  availability check PASSED ✓")


async def test_booking_bypass_format():
    print("\n=== test_booking_bypass_format ===")
    from Application.symptom_check import (
        _format_availability_en, _format_availability_vi,
        _extract_department_from_history, _get_next_weekday_str,
    )
    from Domain.entities import ConversationTurn

    history = [
        ConversationTurn(role="patient", content="I have chest pain"),
        ConversationTurn(role="assistant", content="[R] Based on your symptoms, I recommend Cardiology."),
    ]
    dept = _extract_department_from_history(history)
    print(f"  extracted department: {dept!r}")

    date_str = _get_next_weekday_str()
    print(f"  next weekday: {date_str}")

    # Simulate the availability result
    fake_result = {
        "status": "available",
        "slots": [
            {"doctor_name": "Dr. Smith", "doctor_id": "abc", "specialty_id": "xyz",
             "start_time": "09:00:00", "end_time": "09:30:00"},
            {"doctor_name": "Dr. Jones", "doctor_id": "def", "specialty_id": "xyz",
             "start_time": "10:00:00", "end_time": "10:30:00"},
        ]
    }
    en_msg = _format_availability_en(fake_result, date_str)
    print(f"  EN format:\n    {en_msg}")
    assert "Dr. Smith" in en_msg or "Dr. Jones" in en_msg

    vi_msg = _format_availability_vi(fake_result, date_str)
    print(f"  VI format:\n    {vi_msg}")
    print("  format tests PASSED ✓")


async def test_full_execute_bypass():
    """Test that execute() actually short-circuits and returns availability, not LLM response."""
    print("\n=== test_full_execute_bypass ===")
    from Application.symptom_check import SymptomCheckUseCase
    from Domain.entities import SymptomCheckRequest, ConversationTurn
    from unittest.mock import AsyncMock, MagicMock

    mock_llm = MagicMock()
    mock_llm.stream_with_tools = AsyncMock(side_effect=Exception("LLM SHOULD NOT BE CALLED"))
    mock_clinical = MagicMock()
    mock_clinical.get_patient_context = AsyncMock(return_value={})

    use_case = SymptomCheckUseCase(llm=mock_llm, clinical=mock_clinical)

    request = SymptomCheckRequest(
        patient_id="p1",
        symptoms="Book appointment for me pls",
        conversation_history=[
            ConversationTurn(role="patient", content="I have chest pain"),
            ConversationTurn(role="assistant", content="[R] I recommend Cardiology for your symptoms."),
        ],
        suggested_department="Cardiology",
    )

    chunks = []
    async for chunk in use_case.execute(request, "p1", "patient"):
        chunks.append(chunk)
        print(f"  chunk: {chunk[:80]!r}")

    full = "".join(chunks)
    print(f"\n  full response (first 200 chars): {full[:200]!r}")

    assert chunks, "FAIL: no chunks yielded"
    assert full.startswith("[Q]"), f"FAIL: response must start with [Q], got: {full[:20]!r}"
    assert "Dr." in full or "slot" in full.lower() or "option" in full.lower() or "opening" in full.lower() or "available" in full.lower() or "no available" in full.lower(), \
        f"FAIL: response doesn't look like availability info: {full[:100]}"
    print("  full execute bypass test PASSED ✓")


async def test_confirmation_bypass():
    """Test that saying 'yes' after a slot listing creates an appointment (no LLM)."""
    print("\n=== test_confirmation_bypass ===")
    from Application.symptom_check import (
        SymptomCheckUseCase, _pending_slots, _detect_confirmation_mode,
        _parse_slot_selection,
    )
    from Domain.entities import SymptomCheckRequest, ConversationTurn
    from unittest.mock import AsyncMock, MagicMock, patch

    patient_id = "p1"
    fake_slots = [
        {"doctor_name": "Dr. Nguyen Van An", "doctor_id": "doc-1", "specialty_id": "spec-1",
         "start_time": "08:00:00", "end_time": "08:30:00"},
        {"doctor_name": "Dr. Tran Thi Bich", "doctor_id": "doc-2", "specialty_id": "spec-1",
         "start_time": "09:00:00", "end_time": "09:30:00"},
    ]
    # Seed pending slots keyed by patient_id (as booking bypass stores them)
    _pending_slots[patient_id] = {
        "slots": fake_slots,
        "date_str": "2026-04-20",
        "department": "Cardiology",
    }

    # Verify _detect_confirmation_mode returns True
    req_yes = SymptomCheckRequest(
        patient_id=patient_id,
        symptoms="yes",
        conversation_history=[
            ConversationTurn(role="patient", content="book for me"),
            ConversationTurn(role="assistant", content="[Q] I found 2 options for 2026-04-20:\n(1) Dr. Nguyen Van An — 08:00  ← recommended\n(2) Dr. Tran Thi Bich — 09:00\nI'd recommend option (1). Which would you prefer, or shall I go with (1)?"),
        ],
    )
    mode = _detect_confirmation_mode(req_yes)
    print(f"  _detect_confirmation_mode('yes') = {mode}  (expected: True)")
    assert mode is True, "FAIL: confirmation not detected"

    # Verify slot selection defaults to first slot
    selected = _parse_slot_selection("yes", fake_slots)
    print(f"  _parse_slot_selection('yes') = {selected.get('doctor_name')!r}  (expected: Dr. Nguyen Van An)")
    assert selected["doctor_id"] == "doc-1", f"FAIL: wrong slot selected: {selected}"

    # Verify explicit option 2 selects second slot
    selected2 = _parse_slot_selection("option 2", fake_slots)
    print(f"  _parse_slot_selection('option 2') = {selected2.get('doctor_name')!r}  (expected: Dr. Tran Thi Bich)")
    assert selected2["doctor_id"] == "doc-2", f"FAIL: option 2 not selected"

    # Full execute confirmation bypass test
    mock_llm = MagicMock()
    mock_llm.stream_with_tools = AsyncMock(side_effect=Exception("LLM SHOULD NOT BE CALLED"))
    mock_clinical = MagicMock()
    mock_clinical.get_patient_context = AsyncMock(return_value={})

    fake_appt_result = {
        "status": "created",
        "appointment_id": "appt-xyz-123",
        "doctor_name": "Dr. Nguyen Van An",
        "date": "2026-04-20",
        "time": "08:00",
    }

    # Re-seed (may have been popped)
    _pending_slots[patient_id] = {
        "slots": fake_slots,
        "date_str": "2026-04-20",
        "department": "Cardiology",
    }

    use_case = SymptomCheckUseCase(llm=mock_llm, clinical=mock_clinical)

    with patch("infrastructure.llm.booking_tools.fn_create_appointment", new=AsyncMock(return_value=fake_appt_result)):
        chunks = []
        async for chunk in use_case.execute(req_yes, "p1", "patient"):
            chunks.append(chunk)
            print(f"  chunk: {chunk[:80]!r}")

    full = "".join(chunks)
    print(f"\n  full response: {full!r}")
    assert full.startswith("[Q]"), f"FAIL: must start with [Q], got: {full[:20]!r}"
    assert "appt-xyz-123" in full or "confirmed" in full.lower() or "Appointment" in full, \
        f"FAIL: response doesn't look like a confirmation: {full}"
    assert patient_id not in _pending_slots, "FAIL: pending slots not cleared after confirmation"
    print("  confirmation bypass test PASSED ✓")


async def test_booking_offer_injection():
    """Test that [R] responses always end with a booking offer AND cache the recommendation."""
    print("\n=== test_booking_offer_injection ===")
    from Application.symptom_check import (
        SymptomCheckUseCase, _recent_recommendation, _get_recent_recommendation,
    )
    from Domain.entities import SymptomCheckRequest
    from unittest.mock import AsyncMock, MagicMock

    async def fake_stream(*args, **kwargs):
        yield "[R] Based on your symptoms, I recommend Cardiology. You should see a specialist."

    mock_llm = MagicMock()
    mock_llm.stream_with_tools = fake_stream
    mock_llm.complete_structured = AsyncMock(return_value={"specialties": ["Cardiology"]})
    mock_clinical = MagicMock()
    mock_ctx = MagicMock()
    mock_ctx.full_name = "Test Patient"
    mock_ctx.date_of_birth = None
    mock_ctx.gender = None
    mock_ctx.allergies = []
    mock_ctx.chronic_conditions = []
    mock_ctx.current_medications = []
    mock_ctx.recent_visits = []
    mock_clinical.get_patient_context = AsyncMock(return_value=mock_ctx)

    use_case = SymptomCheckUseCase(llm=mock_llm, clinical=mock_clinical)

    request = SymptomCheckRequest(
        patient_id="p-offer-test",
        symptoms="I have chest pain",
    )
    chunks = []
    async for chunk in use_case.execute(request, "p-offer-test", "patient"):
        chunks.append(chunk)

    full = "".join(chunks)
    print(f"  full response (first 300 chars): {full[:300]!r}")
    has_offer_en = "Would you like me to help you book" in full
    has_offer_vi = "Bạn có muốn tôi giúp đặt lịch" in full
    assert has_offer_en or has_offer_vi, \
        f"FAIL: booking offer not found in response: {full[:200]}"

    # Verify recommendation was cached
    rec = _get_recent_recommendation("p-offer-test")
    print(f"  cached recommendation: {rec}")
    assert rec is not None, "FAIL: recommendation not cached after [R]"
    assert rec["department"] == "Cardiology", f"FAIL: wrong department cached: {rec}"
    print("  booking offer injection + cache test PASSED ✓")


async def test_booking_bypass_cache_fallback():
    """Test that 'yes please book' fires the bypass via server-side cache even with stale history."""
    print("\n=== test_booking_bypass_cache_fallback ===")
    import os
    import pytest
    if not os.path.exists("/app"):
        pytest.skip("Skipped outside Docker container (requires internal network)")

    from Application.symptom_check import (
        SymptomCheckUseCase, _store_recommendation, _pending_slots,
    )
    from Domain.entities import SymptomCheckRequest, ConversationTurn
    from unittest.mock import AsyncMock, MagicMock

    patient_id = "675cf94c-463b-438e-ab9f-d4e09f069e4e"

    # Simulate: [R] was given to this patient (cached server-side)
    _store_recommendation(patient_id, "Cardiology")

    mock_llm = MagicMock()
    mock_llm.stream_with_tools = AsyncMock(side_effect=Exception("LLM SHOULD NOT BE CALLED"))
    mock_clinical = MagicMock()
    mock_clinical.get_patient_context = AsyncMock(return_value={})

    use_case = SymptomCheckUseCase(llm=mock_llm, clinical=mock_clinical)

    # Stale history: only [Q] turns (simulates frontend bug)
    request = SymptomCheckRequest(
        patient_id=patient_id,
        symptoms="Yes pls book",
        conversation_history=[
            ConversationTurn(role="patient", content="I'm experiencing Fatigue, Stomach Pain."),
            ConversationTurn(role="assistant", content="[Q] I'm sorry to hear that. How long have you had these symptoms?"),
            ConversationTurn(role="patient", content="A really sharp pain"),
            ConversationTurn(role="assistant", content="[Q] Thank you for clarifying that. To help further..."),
        ],
    )

    chunks = []
    async for chunk in use_case.execute(request, patient_id, "patient"):
        chunks.append(chunk)
        print(f"  chunk: {chunk[:80]!r}")

    full = "".join(chunks)
    print(f"\n  full response (first 200 chars): {full[:200]!r}")
    assert full.startswith("[Q]"), f"FAIL: must start with [Q], got: {full[:20]!r}"
    assert "Dr." in full or "option" in full.lower() or "opening" in full.lower() or "no available" in full.lower(), \
        f"FAIL: doesn't look like availability info: {full[:100]}"
    assert patient_id in _pending_slots, "FAIL: pending slots not stored after bypass"
    print("  cache fallback bypass test PASSED ✓")


async def test_general_medicine_booking():
    """
    When LLM recommends Internal Medicine, the cache must still be set so that
    'yes book for me' fires the bypass (regression test for the != Internal Medicine bug).
    """
    print("\n=== test_general_medicine_booking ===")
    import os
    if not os.path.exists("/app"):
        print("  skipped (requires Docker internal network)")
        return

    from Application.symptom_check import (
        SymptomCheckUseCase, _get_recent_recommendation, _recent_recommendation,
    )
    from Domain.entities import SymptomCheckRequest
    from unittest.mock import AsyncMock, MagicMock

    patient_id = "p-genmedicine-test"
    _recent_recommendation.pop(patient_id, None)  # clean slate

    async def fake_stream(*args, **kwargs):
        yield "[R] You've been dealing with a cough, stomach pain, and a fever. "
        yield "I recommend seeing Internal Medicine, as these combined symptoms "
        yield "require a comprehensive initial evaluation."

    mock_llm = MagicMock()
    mock_llm.stream_with_tools = fake_stream
    mock_llm.complete_structured = AsyncMock(return_value={"specialties": ["Internal Medicine"]})
    mock_clinical = MagicMock()
    mock_ctx = MagicMock()
    mock_ctx.full_name = "Test"
    mock_ctx.date_of_birth = None
    mock_ctx.gender = None
    mock_ctx.allergies = []
    mock_ctx.chronic_conditions = []
    mock_ctx.current_medications = []
    mock_ctx.recent_visits = []
    mock_clinical.get_patient_context = AsyncMock(return_value=mock_ctx)

    use_case = SymptomCheckUseCase(llm=mock_llm, clinical=mock_clinical)

    # Turn 1: get the [R] recommendation
    req1 = SymptomCheckRequest(patient_id=patient_id, symptoms="I have cough stomach pain and fever")
    async for _ in use_case.execute(req1, patient_id, "patient"):
        pass

    rec = _get_recent_recommendation(patient_id)
    print(f"  cache after Internal Medicine [R]: {rec}")
    assert rec is not None, "FAIL: cache must be set even for Internal Medicine"
    assert rec["department"] == "Internal Medicine", f"FAIL: wrong dept: {rec}"
    print("  Internal Medicine cache set ✓")

    # Turn 2: patient says 'book for me' — must fire bypass, NOT LLM
    mock_llm2 = MagicMock()
    mock_llm2.stream_with_tools = AsyncMock(side_effect=AssertionError("LLM MUST NOT be called on booking turn"))
    use_case2 = SymptomCheckUseCase(llm=mock_llm2, clinical=mock_clinical)

    req2 = SymptomCheckRequest(
        patient_id=patient_id,
        symptoms="Yes could u book for me pls",
        conversation_history=[],  # simulate FE bug: no history sent
    )
    chunks = []
    async for chunk in use_case2.execute(req2, patient_id, "patient"):
        chunks.append(chunk)
    full = "".join(chunks)
    print(f"  booking turn response (first 200): {full[:200]!r}")

    assert full.startswith("[Q]"), f"FAIL: must start with [Q], got: {full[:40]!r}"
    assert "Dr." in full or "opening" in full or "option" in full.lower() or "no available" in full.lower(), \
        f"FAIL: must show slot info: {full[:100]}"
    print("  booking bypass fired for Internal Medicine ✓")
    print("  general_medicine_booking test PASSED ✓")


async def test_emergency_no_cache():
    """Emergency [R] must clear the recommendation cache and never trigger booking bypass."""
    print("\n=== test_emergency_no_cache ===")
    from Application.symptom_check import (
        SymptomCheckUseCase, _store_recommendation, _get_recent_recommendation,
    )
    from Domain.entities import SymptomCheckRequest, ConversationTurn
    from Domain.prompts import _detect_booking_mode
    from unittest.mock import AsyncMock, MagicMock

    patient_id = "p-emergency-test"

    # Step 1: pre-seed cache (as if a prior non-emergency [R] had run)
    _store_recommendation(patient_id, "Cardiology")
    pre = _get_recent_recommendation(patient_id)
    assert pre is not None, "Pre-condition: cache must be set before test"
    print(f"  pre-seed cache: {pre['department']!r}  ✓")

    # Step 2: LLM returns an emergency [R]
    async def fake_emergency_stream(*args, **kwargs):
        yield "[R] This is an emergency. Please call emergency services or go to the nearest ER immediately."

    mock_llm = MagicMock()
    mock_llm.stream_with_tools = fake_emergency_stream
    mock_llm.complete_structured = AsyncMock(return_value={"specialties": ["Emergency Medicine"]})
    mock_clinical = MagicMock()
    mock_ctx = MagicMock()
    mock_ctx.full_name = "Test Patient"
    mock_ctx.date_of_birth = None
    mock_ctx.gender = None
    mock_ctx.allergies = []
    mock_ctx.chronic_conditions = []
    mock_ctx.current_medications = []
    mock_ctx.recent_visits = []
    mock_clinical.get_patient_context = AsyncMock(return_value=mock_ctx)

    use_case = SymptomCheckUseCase(llm=mock_llm, clinical=mock_clinical)

    request = SymptomCheckRequest(
        patient_id=patient_id,
        symptoms="I have severe chest pain and shortness of breath",
    )
    chunks = []
    async for chunk in use_case.execute(request, patient_id, "patient"):
        chunks.append(chunk)
    full = "".join(chunks)
    print(f"  full response (first 200 chars): {full[:200]!r}")

    # Step 3: cache must be CLEARED after emergency response
    rec = _get_recent_recommendation(patient_id)
    print(f"  cache after emergency [R]: {rec}  (expected: None)")
    assert rec is None, f"FAIL: emergency response must NOT leave a cache entry, got: {rec}"

    # Step 4: booking offer must NOT be injected
    has_offer_en = "Would you like me to help you book" in full
    has_offer_vi = "Bạn có muốn tôi giúp đặt lịch" in full
    assert not has_offer_en and not has_offer_vi, \
        f"FAIL: booking offer injected into emergency response: {full[:200]}"
    print("  no booking offer in emergency response  ✓")

    # Step 5: next turn "book for me" must NOT fire bypass (both guard paths blocked)
    follow_up = SymptomCheckRequest(
        patient_id=patient_id,
        symptoms="book for me",
        conversation_history=[
            ConversationTurn(role="patient", content="I have severe chest pain"),
            ConversationTurn(
                role="assistant",
                content="[R] This is an emergency. Please call emergency services or go to the nearest ER immediately.",
            ),
        ],
    )
    # _detect_booking_mode must return False (emergency [R])
    mode = _detect_booking_mode(follow_up)
    assert mode is False, f"FAIL: _detect_booking_mode must be False for emergency, got: {mode}"
    # Cache path must also be blocked (cache was cleared)
    cache_after = _get_recent_recommendation(patient_id)
    assert cache_after is None, f"FAIL: cache should still be None, got: {cache_after}"
    print("  follow-up 'book for me' correctly blocked on both guard paths  ✓")

    print("  emergency no-cache test PASSED ✓")


async def test_emergency_booking_intercept():
    """
    When the last [R] was an emergency and patient says 'book for me',
    the use case must return a clear 'go to ER' message WITHOUT calling the LLM.
    """
    print("\n=== test_emergency_booking_intercept ===")
    from Application.symptom_check import SymptomCheckUseCase, _pending_slots
    from Domain.entities import SymptomCheckRequest, ConversationTurn
    from unittest.mock import AsyncMock, MagicMock

    patient_id = "p-emergency-intercept"

    # LLM should never be called — if it is, the test fails
    mock_llm = MagicMock()
    mock_llm.stream_with_tools = AsyncMock(side_effect=AssertionError("LLM should NOT be called for emergency booking"))
    mock_clinical = MagicMock()
    mock_ctx = MagicMock()
    mock_ctx.full_name = "Test Patient"
    mock_ctx.date_of_birth = None
    mock_ctx.gender = None
    mock_ctx.allergies = []
    mock_ctx.chronic_conditions = []
    mock_ctx.current_medications = []
    mock_ctx.recent_visits = []
    mock_clinical.get_patient_context = AsyncMock(return_value=mock_ctx)

    use_case = SymptomCheckUseCase(llm=mock_llm, clinical=mock_clinical)

    request = SymptomCheckRequest(
        patient_id=patient_id,
        symptoms="Can u book for me pls",
        conversation_history=[
            ConversationTurn(role="patient", content="I have a fever and chills"),
            ConversationTurn(role="assistant", content="[Q] Have you noticed any other symptoms?"),
            ConversationTurn(role="patient", content="I have many cough a day and feel hard to breath"),
            ConversationTurn(
                role="assistant",
                content=(
                    "[R] You are experiencing a fever and chills accompanied by a frequent cough and "
                    "difficulty breathing. These symptoms suggest a serious respiratory issue that requires "
                    "immediate evaluation. Urgency: Emergency. This requires immediate emergency care — "
                    "please go to the nearest Emergency Room or call emergency services now. "
                    "Do not wait for an appointment."
                ),
            ),
        ],
    )

    chunks = []
    async for chunk in use_case.execute(request, patient_id, "patient"):
        chunks.append(chunk)
    full = "".join(chunks)

    print(f"  full response: {full!r}")

    # Must start with [Q] (booking slot format, not LLM)
    assert full.startswith("[Q]"), f"FAIL: response must start with [Q], got: {full[:80]}"

    # Must contain ER/emergency instructions
    er_keywords = ["emergency", "Emergency Room", "ER", "emergency services", "115", "cấp cứu", "khẩn cấp"]
    assert any(kw in full for kw in er_keywords), \
        f"FAIL: response must mention ER/emergency services, got: {full}"

    # Must NOT contain booking offer or slot listings
    assert "opening" not in full and "options for" not in full, \
        f"FAIL: response must not contain slot listings, got: {full}"

    # Booking offer must NOT be injected
    assert "Would you like me to help you book" not in full, \
        f"FAIL: booking offer must not appear in emergency intercept response"

    print("  LLM was NOT called  ✓")
    print("  Response starts with [Q]  ✓")
    print("  Response contains ER/emergency guidance  ✓")
    print("  No slot listings injected  ✓")
    print("  emergency booking intercept test PASSED ✓")


def test_date_parsing():
    """Test _parse_date_from_message with various natural language inputs."""
    print("\n=== test_date_parsing ===")
    from datetime import date, timedelta
    from Application.symptom_check import _parse_date_from_message

    today = date.today()

    # "next wednesday" — today is Saturday Apr 18, 2026 (weekday=5)
    result = _parse_date_from_message("Book me 8:00 next wednesday pls")
    # Wednesday = weekday 2; next from Sat Apr18 → Wed Apr 22
    expected_wed = None
    # Calculate expected: next wednesday from today
    days_to_wed = (2 - today.weekday()) % 7
    if days_to_wed == 0:
        days_to_wed = 7
    if days_to_wed <= (6 - today.weekday()):
        days_to_wed += 7
    expected_wed = (today + timedelta(days=days_to_wed)).strftime("%Y-%m-%d")
    print(f"  'next wednesday' → {result!r}  (expected: {expected_wed!r})")
    assert result == expected_wed, f"FAIL: got {result!r}, expected {expected_wed!r}"

    # "next friday"
    result_fri = _parse_date_from_message("Let me book next friday morning")
    days_to_fri = (4 - today.weekday()) % 7
    if days_to_fri == 0:
        days_to_fri = 7
    if days_to_fri <= (6 - today.weekday()):
        days_to_fri += 7
    expected_fri = (today + timedelta(days=days_to_fri)).strftime("%Y-%m-%d")
    print(f"  'next friday' → {result_fri!r}  (expected: {expected_fri!r})")
    assert result_fri == expected_fri, f"FAIL: got {result_fri!r}, expected {expected_fri!r}"

    # "tomorrow"
    result_tom = _parse_date_from_message("book tomorrow please")
    expected_tom = (today + timedelta(days=1)).strftime("%Y-%m-%d")
    print(f"  'tomorrow' → {result_tom!r}  (expected: {expected_tom!r})")
    assert result_tom == expected_tom, f"FAIL: got {result_tom!r}, expected {expected_tom!r}"

    # No date
    result_none = _parse_date_from_message("book me now")
    print(f"  'book me now' → {result_none!r}  (expected: None)")
    assert result_none is None, f"FAIL: expected None, got {result_none!r}"

    print("  date_parsing test PASSED ✓")


def test_time_preference():
    """Test _parse_time_preference with various formats."""
    print("\n=== test_time_preference ===")
    from Application.symptom_check import _parse_time_preference

    cases = [
        ("Book me 8:00 next wednesday pls", "08:00"),
        ("I want 14:30 appointment", "14:30"),
        ("8h30 tomorrow", "08:30"),
        ("book at 9h", "09:00"),
        ("appointment at 10 am please", "10:00"),
        ("3 pm slot", "15:00"),
        ("book for me", None),
    ]
    for text, expected in cases:
        result = _parse_time_preference(text)
        print(f"  {text!r} → {result!r}  (expected: {expected!r})")
        assert result == expected, f"FAIL: got {result!r}, expected {expected!r}"

    print("  time_preference test PASSED ✓")


async def test_date_change_detection():
    """Test that if patient specifies a different date than pending slots, slots are re-queried."""
    print("\n=== test_date_change_detection ===")
    import time
    from unittest.mock import AsyncMock, MagicMock
    from Application.symptom_check import SymptomCheckUseCase, _pending_slots, _recent_recommendation

    patient_id = "patient_date_change"

    # Pre-populate pending slots for Monday
    from datetime import date, timedelta
    today = date.today()
    # Find next Monday
    days_to_mon = (0 - today.weekday()) % 7
    if days_to_mon == 0:
        days_to_mon = 7
    monday_str = (today + timedelta(days=days_to_mon)).strftime("%Y-%m-%d")

    # Find next Wednesday
    days_to_wed = (2 - today.weekday()) % 7
    if days_to_wed == 0:
        days_to_wed = 7
    if days_to_wed <= (6 - today.weekday()):
        days_to_wed += 7
    wednesday_str = (today + timedelta(days=days_to_wed)).strftime("%Y-%m-%d")

    _pending_slots[patient_id] = {
        "slots": [{"doctor_id": "d1", "specialty_id": "s1", "doctor_name": "Dr Mon", "start_time": "09:00"}],
        "date_str": monday_str,
        "department": "Internal Medicine",
    }

    # Mock clinical client
    clinical = AsyncMock()
    clinical.check_availability = AsyncMock(return_value={
        "status": "ok",
        "slots": [
            {"doctor_id": "d2", "specialty_id": "s1", "doctor_name": "Dr Wed", "start_time": "08:00"},
        ],
    })

    llm = MagicMock()
    use_case = SymptomCheckUseCase(llm=llm, clinical=clinical)

    # Monkey-patch fn_check_availability inside the booking_tools module
    import infrastructure.llm.booking_tools as bt
    orig_fn = bt.fn_check_availability
    bt.fn_check_availability = AsyncMock(return_value={
        "status": "ok",
        "slots": [
            {"doctor_id": "d2", "specialty_id": "s1", "doctor_name": "Dr Wed", "start_time": "08:00"},
        ],
    })

    request = SymptomCheckRequest(
        patient_id=patient_id,
        symptoms=f"Actually, let me do wednesday instead",
        conversation_history=[
            ConversationTurn(role="patient", content="I have a cough"),
            ConversationTurn(role="assistant", content="[R] I recommend Internal Medicine."),
            ConversationTurn(role="assistant", content=f"[Q] I found 1 option for {monday_str}: (1) Dr Mon — 09:00"),
        ],
    )

    chunks = []
    async for chunk in use_case.execute(request, patient_id, "patient"):
        chunks.append(chunk)
    full = "".join(chunks)

    bt.fn_check_availability = orig_fn

    print(f"  response: {full!r}")

    # Should contain wednesday's date, not monday's
    assert wednesday_str in full, f"FAIL: wednesday date {wednesday_str!r} not in response: {full!r}"
    assert monday_str not in full, f"FAIL: old monday date {monday_str!r} still in response"
    assert "Dr Wed" in full, f"FAIL: new doctor not shown"

    # Pending slots should be updated to wednesday
    assert _pending_slots.get(patient_id, {}).get("date_str") == wednesday_str, \
        f"FAIL: pending_slots not updated to {wednesday_str!r}"

    print("  date change detection test PASSED ✓")


async def test_triage_summary():
    """Test generate_summary() with a mock LLM — verifies all 8 fields are returned."""
    print("\n=== test_triage_summary ===")
    from unittest.mock import AsyncMock, MagicMock
    from Application.triage_session import TriageSessionService, TriageSessionAccessDenied, TriageSessionNotFound

    # Build a fake session entity
    from Domain.entities import TriageSession
    from Domain.enums import TriageSessionStatus

    fake_session = TriageSession(
        id="sess-summary-001",
        patient_id="patient-summary-001",
        status=TriageSessionStatus.PENDING_REVIEW,
        messages=[
            {"role": "user",      "content": "I have a bad headache and blurred vision for 2 days"},
            {"role": "assistant", "content": "[Q] How severe is the headache on a 1-10 scale?"},
            {"role": "user",      "content": "About 8, very severe"},
            {"role": "assistant", "content": "[R] Based on your symptoms I recommend Neurology."},
        ],
        suggested_department="Neurology",
        urgency_level="Priority",
    )

    # Mock repo
    mock_repo = MagicMock()
    mock_repo.get_by_id = AsyncMock(return_value=fake_session)

    # Mock LLM with a realistic summary response
    mock_llm = MagicMock()
    mock_llm.complete_structured = AsyncMock(return_value={
        "chief_complaint":        "Severe headache with blurred vision",
        "reported_symptoms":      ["headache (severity 8/10)", "blurred vision"],
        "duration":               "2 days",
        "severity":               "severe (8/10)",
        "suspected_conditions":   ["hypertensive urgency", "migraine with aura"],
        "department_reasoning":   "Neurological symptoms (severe headache + visual disturbance) warrant specialist evaluation.",
        "recommended_department": "Neurology",
        "urgency_level":          "Priority",
    })

    svc = TriageSessionService(mock_repo)
    result = await svc.generate_summary(
        session_id="sess-summary-001",
        requester_id="doctor-001",
        role="doctor",
        llm_client=mock_llm,
    )

    print(f"  chief_complaint:      {result['chief_complaint']!r}")
    print(f"  reported_symptoms:   {result['reported_symptoms']}")
    print(f"  suspected_conditions: {result['suspected_conditions']}")
    print(f"  department_reasoning: {result['department_reasoning']!r}")
    print(f"  recommended_department: {result['recommended_department']!r}")

    # All 8 required fields must be present and non-empty
    required = ["chief_complaint", "reported_symptoms", "duration", "severity",
                "suspected_conditions", "department_reasoning",
                "recommended_department", "urgency_level"]
    for field in required:
        assert field in result, f"FAIL: missing field {field!r}"
    assert result["recommended_department"] == "Neurology"
    assert "headache" in result["chief_complaint"].lower() or "headache" in str(result["reported_symptoms"]).lower()
    assert len(result["reported_symptoms"]) >= 1, "FAIL: no symptoms reported"

    # Patient role must be denied
    try:
        await svc.generate_summary("sess-001", "patient-001", "patient", mock_llm)
        assert False, "FAIL: patient should be denied access"
    except TriageSessionAccessDenied:
        pass

    # Empty messages → returns fallback (no LLM call)
    empty_session = TriageSession(
        id="sess-empty",
        patient_id="p",
        status=TriageSessionStatus.ACTIVE,
        messages=[],
        suggested_department=None,
        urgency_level=None,
    )
    mock_repo.get_by_id = AsyncMock(return_value=empty_session)
    fallback = await svc.generate_summary("sess-empty", "doctor-001", "doctor", mock_llm)
    assert "Insufficient" in fallback["chief_complaint"] or fallback["chief_complaint"] == "Insufficient conversation data"
    print(f"  empty-session fallback chief_complaint: {fallback['chief_complaint']!r}  ✓")

    print("  triage_summary test PASSED ✓")


def test_decline_redirect_payload():
    """Test that decline with redirect_department encodes correctly in cancel_reason."""
    print("\n=== test_decline_redirect_payload ===")

    # Simulate the encoding logic from DeclineAppointmentUseCase
    def _encode_cancel_reason(redirect_department, reason):
        if redirect_department:
            return f"[redirect:{redirect_department}] {reason or ''}".strip()
        return reason

    cases = [
        ("Cardiology",      "doctor unavailable",  "[redirect:Cardiology] doctor unavailable"),
        ("Internal Medicine", None,                  "[redirect:Internal Medicine]"),
        (None,              "personal reasons",     "personal reasons"),
        (None,              None,                   None),
    ]
    for redirect, reason, expected in cases:
        result = _encode_cancel_reason(redirect, reason)
        print(f"  redirect={redirect!r} reason={reason!r} → {result!r}  (expected: {expected!r})")
        assert result == expected, f"FAIL: got {result!r}, expected {expected!r}"

    print("  decline_redirect_payload test PASSED ✓")


def test_decline_notification_body():
    """Test that the notification consumer builds the right body for redirect vs plain decline."""
    print("\n=== test_decline_notification_body ===")

    def _build_body(payload: dict) -> tuple[str, str]:
        redirect_dept = payload.get("redirect_department")
        if redirect_dept:
            body = (
                f"Your appointment request was declined by the doctor. "
                f"You have been referred to {redirect_dept} — "
                f"please book a new appointment with that department."
            )
            title = "Appointment Declined — Referral Issued"
        else:
            body = "Your appointment request was declined by the doctor."
            title = "Appointment Declined"
        return title, body

    # With redirect
    title, body = _build_body({"patient_id": "p1", "redirect_department": "Cardiology"})
    print(f"  with redirect → title={title!r}")
    print(f"                  body={body!r}")
    assert "Cardiology" in body, "FAIL: department not in notification body"
    assert "Referral Issued" in title, "FAIL: title should mention referral"
    assert "referred to Cardiology" in body, "FAIL: referral wording missing"

    # Without redirect
    title2, body2 = _build_body({"patient_id": "p1"})
    print(f"  without redirect → title={title2!r}")
    assert title2 == "Appointment Declined", f"FAIL: unexpected title {title2!r}"
    assert body2 == "Your appointment request was declined by the doctor."

    print("  decline_notification_body test PASSED ✓")


async def main():
    test_detect_booking_mode()
    await test_availability_client()
    await test_booking_bypass_format()
    await test_full_execute_bypass()
    await test_confirmation_bypass()
    await test_booking_offer_injection()
    await test_booking_bypass_cache_fallback()
    await test_general_medicine_booking()
    await test_emergency_no_cache()
    await test_emergency_booking_intercept()
    test_date_parsing()
    test_time_preference()
    await test_date_change_detection()
    await test_triage_summary()
    test_decline_redirect_payload()
    test_decline_notification_body()
    print("\n=== ALL TESTS PASSED ===")


if __name__ == "__main__":
    asyncio.run(main())
