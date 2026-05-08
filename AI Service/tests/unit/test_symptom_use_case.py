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
    def __init__(self, chunks=None):
        self.last_messages = None
        self._chunks = chunks if chunks is not None else ["[Q]", " chunk1", " chunk2"]

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



