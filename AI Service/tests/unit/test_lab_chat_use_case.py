"""
Unit tests for Application/lab_chat.py — LabChatUseCase.

External dependencies (GroqClient, ClinicalClient, QdrantRetriever) are
replaced with Fake objects.  No real I/O occurs.
"""

import asyncio
import pytest

from Application.lab_chat import LabChatUseCase
from Domain.entities import PatientContext


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _yield_control():
    await asyncio.sleep(0)


def _collect_chunks(gen) -> list[str]:
    """Run an async generator to completion and collect all yielded strings."""
    async def _run():
        result = []
        async for chunk in gen:
            result.append(chunk)
        return result
    return asyncio.get_event_loop().run_until_complete(_run())


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

class FakeGroqClient:
    def __init__(self, chunks=None):
        self.last_messages = None
        self.last_kwargs = {}
        self._chunks = chunks or ["Lab result chunk A", " chunk B"]

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
            patient_id="p-001",
            full_name="Test Patient",
            age=40,
            gender="male",
        )

    async def get_patient_context(self, patient_id, x_user_id, x_user_role):
        self.call_count += 1
        self.last_patient_id = patient_id
        await _yield_control()
        return self._context


class FakeRetriever:
    def __init__(self, context_text="KB context chunk"):
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
async def test_streams_all_groq_chunks():
    groq = FakeGroqClient(["chunk1", " chunk2", " chunk3"])
    uc = LabChatUseCase(llm=groq, clinical=FakeClinicalClient())

    chunks = []
    async for c in uc.execute("What is HbA1c?", "u-1", "patient"):
        chunks.append(c)

    # Must contain the 3 Groq chunks
    assert "chunk1" in chunks
    assert " chunk2" in chunks
    assert " chunk3" in chunks


@pytest.mark.asyncio
async def test_patient_role_appends_disclaimer():
    groq = FakeGroqClient(["response"])
    uc = LabChatUseCase(llm=groq, clinical=FakeClinicalClient())

    chunks = []
    async for c in uc.execute("HbA1c là gì?", "u-1", "patient"):
        chunks.append(c)

    full = "".join(chunks)
    # Disclaimer must be present (either Vietnamese or English)
    assert any(kw in full for kw in ["AI", "bác sĩ", "physician", "disclaimer", "⚠"])


@pytest.mark.asyncio
async def test_doctor_role_no_disclaimer():
    groq = FakeGroqClient(["clinical response"])
    uc = LabChatUseCase(llm=groq, clinical=FakeClinicalClient())

    chunks = []
    async for c in uc.execute("Interpret HbA1c 9.2%", "u-1", "doctor"):
        chunks.append(c)

    full = "".join(chunks)
    # The AI_DISCLAIMER text is very specific and should NOT appear for doctor
    assert "Vui lòng trao đổi trực tiếp" not in full
    assert "AI-generated content is not a substitute" not in full


@pytest.mark.asyncio
async def test_admin_role_treated_as_doctor_no_disclaimer():
    groq = FakeGroqClient(["admin response"])
    uc = LabChatUseCase(llm=groq, clinical=FakeClinicalClient())

    chunks = []
    async for c in uc.execute("WBC 14 — significant?", "u-1", "admin"):
        chunks.append(c)

    full = "".join(chunks)
    assert "Vui lòng trao đổi trực tiếp" not in full


# ---------------------------------------------------------------------------
# Tests: patient context fetch
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_patient_context_fetched_when_patient_id_provided():
    groq = FakeGroqClient()
    clinical = FakeClinicalClient()
    uc = LabChatUseCase(llm=groq, clinical=clinical)

    async for _ in uc.execute("What is my WBC?", "u-1", "patient", patient_id="p-999"):
        pass

    assert clinical.call_count == 1
    assert clinical.last_patient_id == "p-999"


@pytest.mark.asyncio
async def test_no_patient_fetch_when_patient_id_is_none():
    groq = FakeGroqClient()
    clinical = FakeClinicalClient()
    uc = LabChatUseCase(llm=groq, clinical=clinical)

    async for _ in uc.execute("What is HbA1c?", "u-1", "patient", patient_id=None):
        pass

    assert clinical.call_count == 0


@pytest.mark.asyncio
async def test_patient_context_block_included_in_messages():
    """If patient_id is given, patient context should appear in the system message."""
    groq = FakeGroqClient()
    clinical = FakeClinicalClient(
        context=PatientContext(
            patient_id="p-xyz",
            full_name="Nguyễn Văn A",
            age=35,
            gender="male",
        )
    )
    uc = LabChatUseCase(llm=groq, clinical=clinical)

    async for _ in uc.execute("Explain my results", "u-1", "doctor", patient_id="p-xyz"):
        pass

    system_msg = groq.last_messages[0]["content"]
    # Patient name should appear in the context block
    assert "Nguyễn Văn A" in system_msg


# ---------------------------------------------------------------------------
# Tests: RAG integration
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rag_not_called_when_no_retriever():
    groq = FakeGroqClient()
    uc = LabChatUseCase(llm=groq, clinical=FakeClinicalClient(), retriever=None)

    # Should not raise, just skip RAG
    async for _ in uc.execute("HbA1c question", "u-1", "doctor"):
        pass


@pytest.mark.asyncio
async def test_rag_called_with_question_and_department():
    groq = FakeGroqClient()
    retriever = FakeRetriever("Guideline context here")
    uc = LabChatUseCase(llm=groq, clinical=FakeClinicalClient(), retriever=retriever)

    async for _ in uc.execute(
        "What does high HbA1c mean?", "u-1", "doctor",
        department="endocrinology"
    ):
        pass

    assert retriever.call_count == 1
    assert retriever.last_query == "What does high HbA1c mean?"
    assert retriever.last_department == "endocrinology"
    assert retriever.last_top_k == 3


@pytest.mark.asyncio
async def test_rag_context_injected_into_system_message():
    groq = FakeGroqClient()
    retriever = FakeRetriever("── KNOWLEDGE BASE CONTEXT ──\nDiabetes guideline text\n── END CONTEXT ──")
    uc = LabChatUseCase(llm=groq, clinical=FakeClinicalClient(), retriever=retriever)

    async for _ in uc.execute("What is HbA1c target?", "u-1", "doctor"):
        pass

    system_msg = groq.last_messages[0]["content"]
    assert "KNOWLEDGE BASE CONTEXT" in system_msg
    assert "Diabetes guideline text" in system_msg


@pytest.mark.asyncio
async def test_rag_empty_context_does_not_pollute_message():
    groq = FakeGroqClient()
    retriever = FakeRetriever("")  # empty context
    uc = LabChatUseCase(llm=groq, clinical=FakeClinicalClient(), retriever=retriever)

    async for _ in uc.execute("Question", "u-1", "doctor"):
        pass

    system_msg = groq.last_messages[0]["content"]
    assert "KNOWLEDGE BASE CONTEXT" not in system_msg


# ---------------------------------------------------------------------------
# Tests: messages structure
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_messages_have_system_and_user_turn():
    groq = FakeGroqClient()
    uc = LabChatUseCase(llm=groq, clinical=FakeClinicalClient())

    async for _ in uc.execute("What is LDL?", "u-1", "doctor"):
        pass

    msgs = groq.last_messages
    assert len(msgs) == 2
    assert msgs[0]["role"] == "system"
    assert msgs[1]["role"] == "user"
    assert msgs[1]["content"] == "What is LDL?"


@pytest.mark.asyncio
async def test_patient_system_prompt_different_from_doctor():
    groq_patient = FakeGroqClient()
    groq_doctor = FakeGroqClient()
    uc_patient = LabChatUseCase(llm=groq_patient, clinical=FakeClinicalClient())
    uc_doctor = LabChatUseCase(llm=groq_doctor, clinical=FakeClinicalClient())

    async for _ in uc_patient.execute("What is glucose?", "u-1", "patient"):
        pass
    async for _ in uc_doctor.execute("What is glucose?", "u-1", "doctor"):
        pass

    system_patient = groq_patient.last_messages[0]["content"]
    system_doctor = groq_doctor.last_messages[0]["content"]
    assert system_patient != system_doctor

