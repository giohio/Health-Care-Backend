import asyncio
import pytest
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from httpx import AsyncClient, ASGITransport

from Application.symptom_check import SymptomCheckUseCase
from Application.triage_session import TriageSessionNotFound
from Domain.entities import ConversationTurn, SymptomCheckRequest, PatientContext, TriageSession
from Domain.enums import TriageSessionStatus
from presentation.routes.symptom import router as symptom_router
from presentation.dependencies import get_symptom_usecase


async def _yield_control():
    await asyncio.sleep(0)


class FakeGroqClient:
    def __init__(self, chunks=None, structured_result=None):
        self.last_messages = None
        self._chunks = chunks if chunks is not None else ["[Q]", " chunk1", " chunk2"]
        self._structured_result = structured_result
        self.structured_calls = []

    async def stream_conversation(self, messages, **kwargs):
        self.last_messages = messages
        await _yield_control()
        for chunk in self._chunks:
            yield chunk

    async def stream_with_tools(self, messages, tools=None, tool_handler=None, **kwargs):
        self.last_messages = messages
        await _yield_control()
        for chunk in self._chunks:
            yield chunk

    async def complete_structured(self, **kwargs):
        await _yield_control()
        self.structured_calls.append(kwargs)
        schema = kwargs.get("response_schema") or {}
        required = set(schema.get("required") or [])
        if "intent" in required and self._structured_result is not None:
            return self._structured_result
        return {"specialties": []}


class FakeClinicalClient:
    def __init__(self, context=None):
        self.called_with = None
        self._context   = context or PatientContext(
            patient_id="p-001",
            full_name="Bệnh nhân",
            age=None,
            gender=None,
        )

    async def get_patient_context(self, patient_id, x_user_id, x_user_role):
        self.called_with = (patient_id, x_user_id, x_user_role)
        await _yield_control()
        return self._context


class FakeTriageState:
    def __init__(self, recommendation=None, pending_slots=None):
        self.recommendation = recommendation
        self.pending_slots = pending_slots
        self.saved_pending_slots = None
        self.deleted_pending = False
        self.deleted_recommendation = False

    async def get_pending_slots(self, patient_id):
        await _yield_control()
        return self.pending_slots

    async def set_pending_slots(self, patient_id, data):
        await _yield_control()
        self.saved_pending_slots = data
        self.pending_slots = data

    async def del_pending_slots(self, patient_id):
        await _yield_control()
        self.deleted_pending = True
        self.pending_slots = None

    async def get_recommendation(self, patient_id):
        await _yield_control()
        return self.recommendation

    async def set_recommendation(self, patient_id, data):
        await _yield_control()
        self.recommendation = data

    async def del_recommendation(self, patient_id):
        await _yield_control()
        self.deleted_recommendation = True
        self.recommendation = None


@pytest.mark.asyncio
async def test_symptom_check_yields_all_chunks():
    groq     = FakeGroqClient(["[Q]", " Xin chào", " đây là câu hỏi."])
    clinical = FakeClinicalClient()
    use_case = SymptomCheckUseCase(llm=groq, clinical=clinical)

    request = SymptomCheckRequest(
        patient_id="p-001",
        symptoms="Đau đầu dữ dội trong 3 ngày",
    )

    chunks = []
    async for chunk in use_case.execute(request, "u-001", "patient"):
        chunks.append(chunk)

    assert "[Q]" in chunks[0]
    assert " Xin chào" in chunks
    assert " đây là câu hỏi." in chunks


@pytest.mark.asyncio
async def test_symptom_check_fetches_patient_context():
    groq     = FakeGroqClient()
    clinical = FakeClinicalClient()
    use_case = SymptomCheckUseCase(llm=groq, clinical=clinical)

    request = SymptomCheckRequest(patient_id="p-002", symptoms="Sốt cao liên tục")

    async for _ in use_case.execute(request, "u-002", "patient"):
        ...  # exhaust generator to trigger side effects

    assert clinical.called_with == ("p-002", "u-002", "patient")


@pytest.mark.asyncio
async def test_symptom_check_includes_patient_name_in_messages():
    context = PatientContext(
        patient_id="p-003",
        full_name="Lê Văn C",
        age=50,
        gender="male",
        active_diagnoses=["Tiểu đường"],
        current_medications=[],
        allergies="",
        chronic_conditions="",
    )
    groq     = FakeGroqClient()
    clinical = FakeClinicalClient(context=context)
    use_case = SymptomCheckUseCase(llm=groq, clinical=clinical)

    request = SymptomCheckRequest(patient_id="p-003", symptoms="Khát nước nhiều, tiểu nhiều")

    async for _ in use_case.execute(request, "u-001", "doctor"):
        ...  # exhaust generator; assertions check messages content

    # System message (index 0) should contain patient info
    system_content = groq.last_messages[0]["content"]
    assert "Lê Văn C" in system_content
    assert "50" in system_content
    assert "Tiểu đường" in system_content


@pytest.mark.asyncio
async def test_symptom_check_appends_disclaimer_on_recommendation_turn():
    groq     = FakeGroqClient(chunks=["[R]", " Đây là đề xuất."])
    clinical = FakeClinicalClient()
    use_case = SymptomCheckUseCase(llm=groq, clinical=clinical)

    request = SymptomCheckRequest(patient_id="p-005", symptoms="Đau ngực kéo dài")

    chunks = []
    async for chunk in use_case.execute(request, "u-001", "patient"):
        chunks.append(chunk)

    full_text = "".join(chunks)
    # Disclaimer should be appended on [R] turns
    assert "AI" in full_text or "trợ lý" in full_text.lower()


@pytest.mark.asyncio
async def test_symptom_check_no_disclaimer_on_question_turn():
    groq     = FakeGroqClient(chunks=["[Q]", " Bạn đau ở đâu?"])
    clinical = FakeClinicalClient()
    use_case = SymptomCheckUseCase(llm=groq, clinical=clinical)

    request = SymptomCheckRequest(patient_id="p-006", symptoms="Đau bụng")

    chunks = []
    async for chunk in use_case.execute(request, "u-001", "patient"):
        chunks.append(chunk)

    # No disclaimer appended on question turns
    full_text = "".join(chunks)
    assert "⚠️" not in full_text
    assert "Lưu ý" not in full_text


@pytest.mark.asyncio
async def test_symptom_check_passes_conversation_history_in_messages():
    groq     = FakeGroqClient()
    clinical = FakeClinicalClient()
    use_case = SymptomCheckUseCase(llm=groq, clinical=clinical)

    history = [
        ConversationTurn(role="patient",   content="Tôi bị đau đầu"),
        ConversationTurn(role="assistant", content="[Q] Đau đầu ở vị trí nào?"),
    ]
    request = SymptomCheckRequest(
        patient_id="p-007",
        symptoms="Đau ở thái dương",
        conversation_history=history,
    )

    async for _ in use_case.execute(request, "u-001", "patient"):
        ...

    # Messages: system + 2 history turns + current user turn = 4 total
    assert len(groq.last_messages) == 4
    assert groq.last_messages[1]["role"] == "user"
    assert groq.last_messages[2]["role"] == "assistant"
    assert groq.last_messages[3]["content"] == "Đau ở thái dương"


@pytest.mark.asyncio
async def test_symptom_check_empty_stream_returns_nothing():
    groq     = FakeGroqClient(chunks=[])
    clinical = FakeClinicalClient()
    use_case = SymptomCheckUseCase(llm=groq, clinical=clinical)

    request = SymptomCheckRequest(patient_id="p-004", symptoms="Triệu chứng không rõ ràng")
    chunks  = [c async for c in use_case.execute(request, "u-001", "patient")]

    assert chunks == []


@pytest.mark.asyncio
async def test_booking_yes_please_after_recommendation_asks_for_date_without_llm():
    groq = FakeGroqClient(chunks=["[Q]", " should not be called"])
    clinical = FakeClinicalClient()
    use_case = SymptomCheckUseCase(
        llm=groq,
        clinical=clinical,
        state=FakeTriageState(),
    )

    request = SymptomCheckRequest(
        patient_id="p-book-date",
        symptoms="Yes pls",
        conversation_history=[
            ConversationTurn(role="patient", content="I have fever and cough"),
            ConversationTurn(role="assistant", content="[R] I recommend General Medicine. Would you like me to help you book an appointment?"),
        ],
    )

    chunks = [c async for c in use_case.execute(request, "u-001", "patient")]

    assert "".join(chunks) == "[Q] What date would you like to book, or would you prefer the earliest available?"
    assert clinical.called_with is None
    assert groq.last_messages is None


@pytest.mark.asyncio
async def test_booking_yes_oks_after_offer_asks_for_date_without_llm():
    groq = FakeGroqClient(chunks=["[Q]", " should not be called"])
    clinical = FakeClinicalClient()
    use_case = SymptomCheckUseCase(
        llm=groq,
        clinical=clinical,
        state=FakeTriageState(),
    )

    request = SymptomCheckRequest(
        patient_id="p-book-yes-oks",
        symptoms="Yes oks",
        conversation_history=[
            ConversationTurn(role="patient", content="I have fever and cough"),
            ConversationTurn(role="assistant", content="[R] I recommend General Medicine. Would you like me to help you book an appointment?"),
        ],
    )

    chunks = [c async for c in use_case.execute(request, "u-001", "patient")]

    assert "".join(chunks) == "[Q] What date would you like to book, or would you prefer the earliest available?"
    assert clinical.called_with is None
    assert groq.last_messages is None


@pytest.mark.asyncio
async def test_booking_date_answer_after_prompt_checks_availability_after_busy_until_day():
    from Application.symptom_check import _parse_date_from_message

    expected_date = _parse_date_from_message("I'm busy till next tuesday so after that would work")
    assert expected_date is not None

    groq = FakeGroqClient(chunks=["[Q]", " should not be called"])
    clinical = FakeClinicalClient()
    state = FakeTriageState()
    use_case = SymptomCheckUseCase(llm=groq, clinical=clinical, state=state)

    fake_availability = {
        "status": "ok",
        "slots": [
            {
                "doctor_id": "doc-1",
                "specialty_id": "spec-1",
                "doctor_name": "Dr. An",
                "start_time": "09:00:00",
                "end_time": "09:30:00",
            },
        ],
    }

    request = SymptomCheckRequest(
        patient_id="p-book-after",
        symptoms="I'm busy till next tuesday so after that would work",
        conversation_history=[
            ConversationTurn(role="patient", content="I have fever and cough"),
            ConversationTurn(role="assistant", content="[R] I recommend General Medicine. Would you like me to help you book an appointment?"),
            ConversationTurn(role="patient", content="Yes pls"),
            ConversationTurn(role="assistant", content="[Q] What date would you like to book, or would you prefer the earliest available?"),
        ],
    )

    with patch("infrastructure.llm.booking_tools.fn_check_availability", new=AsyncMock(return_value=fake_availability)) as mock_check:
        chunks = [c async for c in use_case.execute(request, "u-001", "patient")]

    full_text = "".join(chunks)
    mock_check.assert_awaited_once_with("General Medicine", expected_date)
    assert f"on {expected_date}" in full_text
    assert "Dr. An" in full_text
    assert state.saved_pending_slots["date_str"] == expected_date
    assert clinical.called_with is None
    assert groq.last_messages is None


@pytest.mark.asyncio
async def test_booking_date_answer_parses_next_week_thurday_typo():
    from Application.symptom_check import _parse_date_from_message

    expected_date = _parse_date_from_message("I'm busy till next week, maybe i will be free on thurday")
    assert expected_date is not None

    groq = FakeGroqClient(chunks=["[Q]", " should not be called"])
    clinical = FakeClinicalClient()
    state = FakeTriageState()
    use_case = SymptomCheckUseCase(llm=groq, clinical=clinical, state=state)

    fake_availability = {
        "status": "ok",
        "slots": [
            {
                "doctor_id": "doc-2",
                "specialty_id": "spec-1",
                "doctor_name": "Dr. Binh",
                "start_time": "10:00:00",
                "end_time": "10:30:00",
            },
        ],
    }

    request = SymptomCheckRequest(
        patient_id="p-book-thurday",
        symptoms="I'm busy till next week, maybe i will be free on thurday",
        conversation_history=[
            ConversationTurn(role="patient", content="I have fever and cough"),
            ConversationTurn(role="assistant", content="[R] I recommend General Medicine. Would you like me to help you book an appointment?"),
            ConversationTurn(role="patient", content="Yes pls"),
            ConversationTurn(role="assistant", content="[Q] What date would you like to book, or would you prefer the earliest available?"),
        ],
    )

    with patch("infrastructure.llm.booking_tools.fn_check_availability", new=AsyncMock(return_value=fake_availability)) as mock_check:
        chunks = [c async for c in use_case.execute(request, "u-001", "patient")]

    full_text = "".join(chunks)
    mock_check.assert_awaited_once_with("General Medicine", expected_date)
    assert "What date would you like to book" not in full_text
    assert f"on {expected_date}" in full_text
    assert "Dr. Binh" in full_text
    assert state.saved_pending_slots["date_str"] == expected_date
    assert clinical.called_with is None
    assert groq.last_messages is None


@pytest.mark.asyncio
async def test_booking_date_answer_uses_semantic_date_when_regex_cannot_parse():
    groq = FakeGroqClient(
        chunks=["[Q]", " should not be streamed"],
        structured_result={
            "intent": "provide_date_constraint",
            "date_constraint": {
                "kind": "after",
                "raw_text": "until the 14th, after that works",
                "normalized_date": "2026-05-15",
            },
            "time_preference": "",
            "confidence": 0.91,
        },
    )
    clinical = FakeClinicalClient()
    state = FakeTriageState()
    use_case = SymptomCheckUseCase(llm=groq, clinical=clinical, state=state)

    fake_availability = {
        "status": "ok",
        "slots": [
            {
                "doctor_id": "doc-3",
                "specialty_id": "spec-1",
                "doctor_name": "Dr. Chi",
                "start_time": "09:00:00",
                "end_time": "09:30:00",
            },
        ],
    }

    request = SymptomCheckRequest(
        patient_id="p-book-semantic-date",
        symptoms="I'm tied up until the 14th, after that works",
        conversation_history=[
            ConversationTurn(role="patient", content="I have fever and cough"),
            ConversationTurn(role="assistant", content="[R] I recommend General Medicine. Would you like me to help you book an appointment?"),
            ConversationTurn(role="patient", content="Yes pls"),
            ConversationTurn(role="assistant", content="[Q] What date would you like to book, or would you prefer the earliest available?"),
        ],
    )

    with patch("infrastructure.llm.booking_tools.fn_check_availability", new=AsyncMock(return_value=fake_availability)) as mock_check:
        chunks = [c async for c in use_case.execute(request, "u-001", "patient")]

    full_text = "".join(chunks)
    mock_check.assert_awaited_once_with("General Medicine", "2026-05-15")
    assert "What date would you like to book" not in full_text
    assert "Dr. Chi" in full_text
    assert state.saved_pending_slots["date_str"] == "2026-05-15"
    assert clinical.called_with is None
    assert groq.last_messages is None


@pytest.mark.asyncio
async def test_booking_semantic_acceptance_after_recommendation_asks_for_date():
    groq = FakeGroqClient(
        chunks=["[Q]", " should not be streamed"],
        structured_result={
            "intent": "accept_booking",
            "date_constraint": {
                "kind": "unknown",
                "raw_text": "",
                "normalized_date": "",
            },
            "time_preference": "",
            "confidence": 0.88,
        },
    )
    clinical = FakeClinicalClient()
    use_case = SymptomCheckUseCase(llm=groq, clinical=clinical, state=FakeTriageState())

    request = SymptomCheckRequest(
        patient_id="p-book-semantic-accept",
        symptoms="Could you arrange that for me?",
        conversation_history=[
            ConversationTurn(role="patient", content="I have fever and cough"),
            ConversationTurn(role="assistant", content="[R] I recommend General Medicine. Would you like me to help you book an appointment?"),
        ],
    )

    chunks = [c async for c in use_case.execute(request, "u-001", "patient")]

    assert "".join(chunks) == "[Q] What date would you like to book, or would you prefer the earliest available?"
    assert clinical.called_with is None
    assert groq.last_messages is None


# ─────────────────────────────────────────────────────────────────────────────
# Route-level tests: session state management and SSE event structure
# ─────────────────────────────────────────────────────────────────────────────
# These tests spin up a minimal FastAPI app with only the symptom router and
# verify the full request → SSE → DB-persist cycle using async mocks so that
# no real Postgres connection is needed.


def _fake_triage_session(session_id: str = "ses-01", messages=None) -> TriageSession:
    return TriageSession(
        id=session_id,
        patient_id="p-001",
        status=TriageSessionStatus.ACTIVE,
        messages=messages or [],
    )


async def _stream_sse(client, payload, headers=None):
    """POST to /symptom-check and collect non-blank SSE lines."""
    _headers = {"x-user-id": "u-001", "x-user-role": "patient"}
    if headers:
        _headers.update(headers)
    lines = []
    async with client.stream("POST", "/symptom-check", json=payload, headers=_headers) as resp:
        async for line in resp.aiter_lines():
            if line:
                lines.append(line)
    return lines


def _make_symptom_app(use_case):
    """Minimal FastAPI app with only the symptom router and one dependency override."""
    app = FastAPI()
    app.include_router(symptom_router)
    app.dependency_overrides[get_symptom_usecase] = lambda: use_case
    return app


@pytest.mark.asyncio
async def test_symptom_route_emits_session_id_as_first_event():
    """First SSE event in the stream must be `event: session_id` so the client can persist it."""
    fake_session = _fake_triage_session("ses-abc")
    mock_svc = AsyncMock()
    mock_svc.start_session.return_value = fake_session
    mock_svc.finish_turn = AsyncMock()

    app = _make_symptom_app(
        SymptomCheckUseCase(
            llm=FakeGroqClient(["[Q]", " Đau từ khi nào?"]),
            clinical=FakeClinicalClient(),
        )
    )

    with patch("presentation.routes.symptom.AsyncSessionLocal") as MockSL, \
         patch("presentation.routes.symptom.TriageSessionService", return_value=mock_svc), \
         patch("presentation.routes.symptom.TriageSessionRepository"):
        MockSL.return_value = AsyncMock()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            lines = await _stream_sse(client, {"patient_id": "p-001", "symptoms": "Đau đầu kéo dài nhiều giờ"})

    assert lines[0] == "event: session_id"
    assert lines[1] == f"data: {fake_session.id}"


@pytest.mark.asyncio
async def test_symptom_route_new_session_calls_start_session():
    """Omitting session_id must trigger TriageSessionService.start_session, not load_session."""
    fake_session = _fake_triage_session("ses-new")
    mock_svc = AsyncMock()
    mock_svc.start_session.return_value = fake_session
    mock_svc.finish_turn = AsyncMock()

    app = _make_symptom_app(
        SymptomCheckUseCase(
            llm=FakeGroqClient(["[Q]", " Bạn sốt bao lâu rồi?"]),
            clinical=FakeClinicalClient(),
        )
    )

    with patch("presentation.routes.symptom.AsyncSessionLocal") as MockSL, \
         patch("presentation.routes.symptom.TriageSessionService", return_value=mock_svc), \
         patch("presentation.routes.symptom.TriageSessionRepository"):
        MockSL.return_value = AsyncMock()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await _stream_sse(client, {"patient_id": "p-001", "symptoms": "Sốt cao kéo dài từ sáng"})

    mock_svc.start_session.assert_called_once_with("p-001")
    mock_svc.load_session.assert_not_called()


@pytest.mark.asyncio
async def test_symptom_route_existing_session_loads_history():
    """Passing session_id must load existing messages as conversation history for Groq."""
    existing_session = _fake_triage_session(
        "ses-existing",
        messages=[
            {"role": "user",      "content": "Tôi bị đau đầu"},
            {"role": "assistant", "content": "[Q] Đau ở vị trí nào?"},
        ],
    )
    mock_svc = AsyncMock()
    mock_svc.load_session.return_value = existing_session
    mock_svc.finish_turn = AsyncMock()

    groq = FakeGroqClient(["[R]", " Khuyến nghị gặp bác sĩ."])
    app  = _make_symptom_app(SymptomCheckUseCase(llm=groq, clinical=FakeClinicalClient()))

    with patch("presentation.routes.symptom.AsyncSessionLocal") as MockSL, \
         patch("presentation.routes.symptom.TriageSessionService", return_value=mock_svc), \
         patch("presentation.routes.symptom.TriageSessionRepository"):
        MockSL.return_value = AsyncMock()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await _stream_sse(
                client,
                {"patient_id": "p-001", "symptoms": "Đau ở thái dương", "session_id": "ses-existing"},
            )

    mock_svc.load_session.assert_called_once_with("ses-existing", "u-001", "patient")
    # system(1) + 2 prior turns + current user message(1) = 4 messages sent to Groq
    assert len(groq.last_messages) == 4


@pytest.mark.asyncio
async def test_symptom_route_unknown_session_returns_404():
    """A session_id that does not exist must produce HTTP 404 before any SSE data."""
    mock_svc = AsyncMock()
    mock_svc.load_session.side_effect = TriageSessionNotFound("not found")

    app = _make_symptom_app(
        SymptomCheckUseCase(llm=FakeGroqClient(), clinical=FakeClinicalClient())
    )

    with patch("presentation.routes.symptom.AsyncSessionLocal") as MockSL, \
         patch("presentation.routes.symptom.TriageSessionService", return_value=mock_svc), \
         patch("presentation.routes.symptom.TriageSessionRepository"):
        MockSL.return_value = AsyncMock()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/symptom-check",
                json={"patient_id": "p-001", "symptoms": "Đau đầu kéo dài nhiều giờ", "session_id": "bad-id"},
                headers={"x-user-id": "u-001", "x-user-role": "patient"},
            )

    assert resp.status_code == 404
