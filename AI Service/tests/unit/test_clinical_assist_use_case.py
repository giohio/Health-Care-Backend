"""
Unit tests for Application/clinical_assist.py — ClinicalAssistUseCase.

Access restriction (doctor/admin only) is enforced in the route layer,
NOT in the use case — these tests exercise the use case directly with any role.
"""

import asyncio
import pytest

from Application.clinical_assist import ClinicalAssistUseCase
from Domain.entities import PatientContext


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _yield_control():
    await asyncio.sleep(0)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

class FakeGroqClient:
    def __init__(self, chunks=None):
        self.last_messages = None
        self.last_kwargs = {}
        self._chunks = chunks or ["Clinical chunk A", " chunk B"]

    async def stream_conversation(self, messages, **kwargs):
        self.last_messages = messages
        self.last_kwargs = kwargs
        await _yield_control()
        for chunk in self._chunks:
            yield chunk


class FakeClinicalClient:
    def __init__(self, context=None):
        self.call_count = 0
        self.last_patient_id = None
        self._context = context or PatientContext(
            patient_id="p-doc-001",
            full_name="Dr. Patient",
            age=55,
            gender="female",
        )

    async def get_patient_context(self, patient_id, x_user_id, x_user_role):
        self.call_count += 1
        self.last_patient_id = patient_id
        await _yield_control()
        return self._context


class FakeRetriever:
    def __init__(self, context_text="Clinical KB context"):
        self.call_count = 0
        self.last_query = None
        self.last_department = None
        self.last_top_k = None
        self._context = context_text

    async def get_context(self, query, department=None, top_k=3):
        self.call_count += 1
        self.last_query = query
        self.last_department = department
        self.last_top_k = top_k
        await _yield_control()
        return self._context


# ---------------------------------------------------------------------------
# Tests: basic streaming
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_streams_all_chunks():
    groq = FakeGroqClient(["chunk1", " chunk2"])
    uc = ClinicalAssistUseCase(llm=groq, clinical=FakeClinicalClient())

    chunks = []
    async for c in uc.execute("Differential for hypertension?", "u-1", "doctor"):
        chunks.append(c)

    assert "chunk1" in chunks
    assert " chunk2" in chunks


@pytest.mark.asyncio
async def test_execute_returns_async_generator():
    groq = FakeGroqClient()
    uc = ClinicalAssistUseCase(llm=groq, clinical=FakeClinicalClient())

    gen = uc.execute("Diagnose fever", "u-1", "doctor")
    # Must be an async generator
    import inspect
    assert inspect.isasyncgen(gen)


@pytest.mark.asyncio
async def test_messages_have_system_and_user_turn():
    groq = FakeGroqClient()
    uc = ClinicalAssistUseCase(llm=groq, clinical=FakeClinicalClient())

    async for _ in uc.execute("What is first-line for HTN?", "u-1", "doctor"):
        pass

    msgs = groq.last_messages
    assert len(msgs) == 2
    assert msgs[0]["role"] == "system"
    assert msgs[1]["role"] == "user"
    assert msgs[1]["content"] == "What is first-line for HTN?"


# ---------------------------------------------------------------------------
# Tests: max_tokens for clinical decisions
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_uses_2048_max_tokens():
    """ClinicalAssistUseCase should request more tokens than LabChat."""
    groq = FakeGroqClient()
    uc = ClinicalAssistUseCase(llm=groq, clinical=FakeClinicalClient())

    async for _ in uc.execute("Complex cardiac case", "u-1", "doctor"):
        pass

    assert groq.last_kwargs.get("max_tokens") == 2048


# ---------------------------------------------------------------------------
# Tests: patient context
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_patient_context_fetched_when_patient_id_provided():
    groq = FakeGroqClient()
    clinical = FakeClinicalClient()
    uc = ClinicalAssistUseCase(llm=groq, clinical=clinical)

    async for _ in uc.execute(
        "Review this patient", "u-1", "doctor", patient_id="p-888"
    ):
        pass

    assert clinical.call_count == 1
    assert clinical.last_patient_id == "p-888"


@pytest.mark.asyncio
async def test_no_patient_fetch_when_patient_id_none():
    groq = FakeGroqClient()
    clinical = FakeClinicalClient()
    uc = ClinicalAssistUseCase(llm=groq, clinical=clinical)

    async for _ in uc.execute("General question about ACE inhibitors", "u-1", "doctor"):
        pass

    assert clinical.call_count == 0


@pytest.mark.asyncio
async def test_patient_context_block_in_system_message():
    groq = FakeGroqClient()
    clinical = FakeClinicalClient(
        context=PatientContext(
            patient_id="p-ctx",
            full_name="Trần Thị B",
            age=62,
            gender="female",
        )
    )
    uc = ClinicalAssistUseCase(llm=groq, clinical=clinical)

    async for _ in uc.execute("Evaluate findings", "u-1", "doctor", patient_id="p-ctx"):
        pass

    system_msg = groq.last_messages[0]["content"]
    assert "Trần Thị B" in system_msg


# ---------------------------------------------------------------------------
# Tests: RAG with top_k=4
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rag_not_called_when_no_retriever():
    groq = FakeGroqClient()
    uc = ClinicalAssistUseCase(llm=groq, clinical=FakeClinicalClient(), retriever=None)

    async for _ in uc.execute("What is KDIGO CKD staging?", "u-1", "doctor"):
        pass
    # No error — retriever is optional


@pytest.mark.asyncio
async def test_rag_called_with_top_k_4():
    """ClinicalAssistUseCase must request top_k=4 (more context than LabChat)."""
    groq = FakeGroqClient()
    retriever = FakeRetriever("KDIGO guidelines text")
    uc = ClinicalAssistUseCase(llm=groq, clinical=FakeClinicalClient(), retriever=retriever)

    async for _ in uc.execute("CKD management", "u-1", "doctor", department="nephrology"):
        pass

    assert retriever.call_count == 1
    assert retriever.last_top_k == 4
    assert retriever.last_department == "nephrology"


@pytest.mark.asyncio
async def test_rag_context_injected_into_system_message():
    groq = FakeGroqClient()
    retriever = FakeRetriever("── KNOWLEDGE BASE CONTEXT ──\nKDIGO 2022 staging\n── END CONTEXT ──")
    uc = ClinicalAssistUseCase(llm=groq, clinical=FakeClinicalClient(), retriever=retriever)

    async for _ in uc.execute("CKD staging", "u-1", "doctor"):
        pass

    system_msg = groq.last_messages[0]["content"]
    assert "KDIGO 2022 staging" in system_msg


@pytest.mark.asyncio
async def test_rag_query_uses_question_text():
    groq = FakeGroqClient()
    retriever = FakeRetriever()
    uc = ClinicalAssistUseCase(llm=groq, clinical=FakeClinicalClient(), retriever=retriever)

    async for _ in uc.execute("First line treatment for T2DM?", "u-1", "doctor"):
        pass

    assert retriever.last_query == "First line treatment for T2DM?"


# ---------------------------------------------------------------------------
# Tests: system prompt content
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_system_prompt_contains_physician_judgment_directive():
    groq = FakeGroqClient()
    uc = ClinicalAssistUseCase(llm=groq, clinical=FakeClinicalClient())

    async for _ in uc.execute("Any question", "u-1", "doctor"):
        pass

    system_content = groq.last_messages[0]["content"]
    assert "physician" in system_content.lower() or "bác sĩ" in system_content.lower()

