"""
Unit tests verifying that the three existing use cases
(SymptomCheckUseCase, LabAnalysisUseCase, EmrSummaryUseCase)
now correctly call the QdrantRetriever and pass rag_context
into their downstream prompts.
"""

import asyncio
import pytest

from Domain.entities import (
    PatientContext,
    SymptomCheckRequest,
    LabAnalysisRequest,
    EmrSummaryRequest,
)
from Domain.enums import InputType, Department


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _yield_control():
    await asyncio.sleep(0)


# ---------------------------------------------------------------------------
# Shared Fakes
# ---------------------------------------------------------------------------

class FakeGroqStreamer:
    """Streaming use case (SymptomCheck, EmrSummary)."""
    def __init__(self, chunks=None):
        self.last_messages = None
        self.last_system_prompt = None
        self.last_user_prompt = None
        self._chunks = chunks or ["[R] chunk A", " chunk B"]

    async def stream_conversation(self, messages, **kwargs):
        self.last_messages = messages
        await _yield_control()
        for c in self._chunks:
            yield c

    async def stream_completion(self, system_prompt, user_prompt, **kwargs):
        self.last_system_prompt = system_prompt
        self.last_user_prompt = user_prompt
        await _yield_control()
        for c in self._chunks:
            yield c

    async def stream_with_tools(self, messages, tools=None, tool_handler=None, **kwargs):
        self.last_messages = messages
        await _yield_control()
        for c in self._chunks:
            yield c

    async def complete_structured(self, **kwargs):
        await _yield_control()
        return {"specialties": []}


class FakeGroqCompleter:
    """Complete (non-streaming) use case (LabAnalysis)."""
    def __init__(self, text="Draft report"):
        self.last_user_prompt = None
        self._text = text

    async def complete(self, system_prompt, user_prompt, **kwargs):
        self.last_user_prompt = user_prompt
        await _yield_control()
        return self._text

    async def complete_structured(self, **kwargs):
        await _yield_control()
        return {}


class FakeGeminiClient:
    async def extract_findings(self, *args, **kwargs):
        await _yield_control()
        return {"confidence": 0.8, "keywords": ["WBC elevated"]}

    async def extract_tabular(self, *args, **kwargs):
        await _yield_control()
        return {"confidence": 0.85, "keywords": ["glucose"]}


class FakeClinicalClient:
    def __init__(self, diagnoses=None):
        self._diagnoses = diagnoses or ["Hypertension"]

    async def get_patient_context(self, patient_id, x_user_id, x_user_role):
        await _yield_control()
        return PatientContext(
            patient_id=patient_id,
            full_name="Test Patient",
            age=50,
            gender="male",
            active_diagnoses=self._diagnoses,
        )


class FakeEmrResultClient:
    async def get_recent_results(self, patient_id, token, x_user_id, x_user_role, limit=5):
        await _yield_control()
        return []


class FakeRetriever:
    def __init__(self, context_text="Relevant KB text"):
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
# SymptomCheckUseCase
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_symptom_check_calls_retriever():
    from Application.symptom_check import SymptomCheckUseCase

    groq = FakeGroqStreamer(["[R] Hô hấp."])
    retriever = FakeRetriever("Respiratory guidelines")
    uc = SymptomCheckUseCase(
        llm=groq,
        clinical=FakeClinicalClient(),
        retriever=retriever,
    )

    req = SymptomCheckRequest(patient_id="p-1", symptoms="Ho khan, khó thở")
    async for _ in uc.execute(req, "u-1", "patient"):
        pass

    assert retriever.call_count == 1
    assert "Ho khan" in retriever.last_query or "khó thở" in retriever.last_query


@pytest.mark.asyncio
async def test_symptom_check_without_retriever_still_works():
    from Application.symptom_check import SymptomCheckUseCase

    groq = FakeGroqStreamer(["[R] Fine."])
    uc = SymptomCheckUseCase(
        llm=groq,
        clinical=FakeClinicalClient(),
        retriever=None,
    )

    req = SymptomCheckRequest(patient_id="p-1", symptoms="Đau đầu")
    chunks = []
    async for c in uc.execute(req, "u-1", "patient"):
        chunks.append(c)

    assert len(chunks) > 0  # did not crash


@pytest.mark.asyncio
async def test_symptom_check_rag_context_injects_into_system_message():
    from Application.symptom_check import SymptomCheckUseCase

    groq = FakeGroqStreamer(["[Q] More info?"])
    retriever = FakeRetriever("── KNOWLEDGE BASE CONTEXT ──\nHeadache guidelines\n── END CONTEXT ──")
    uc = SymptomCheckUseCase(llm=groq, clinical=FakeClinicalClient(), retriever=retriever)

    req = SymptomCheckRequest(patient_id="p-1", symptoms="Migraines")
    async for _ in uc.execute(req, "u-1", "patient"):
        pass

    system_content = groq.last_messages[0]["content"]
    assert "Headache guidelines" in system_content


@pytest.mark.asyncio
async def test_symptom_check_retriever_queries_with_symptoms():
    from Application.symptom_check import SymptomCheckUseCase

    groq = FakeGroqStreamer()
    retriever = FakeRetriever()
    uc = SymptomCheckUseCase(llm=groq, clinical=FakeClinicalClient(), retriever=retriever)

    symptoms = "Sốt cao, đau cơ toàn thân"
    req = SymptomCheckRequest(patient_id="p-2", symptoms=symptoms)
    async for _ in uc.execute(req, "u-1", "patient"):
        pass

    assert retriever.last_query == symptoms


# ---------------------------------------------------------------------------
# LabAnalysisUseCase
# ---------------------------------------------------------------------------

def _lab_request(department=Department.HEMATOLOGY, tabular=True):
    return LabAnalysisRequest(
        result_id="r-lab-001",
        patient_id="p-lab-001",
        file_url="",
        input_type=InputType.TABULAR,
        department=department,
        test_name="CBC",
        tabular_data={"WBC": 14.2, "RBC": 4.5} if tabular else None,
    )


@pytest.mark.asyncio
async def test_lab_analysis_calls_retriever():
    from Application.lab_analysis import LabAnalysisUseCase

    groq = FakeGroqCompleter("Draft CBC report")
    retriever = FakeRetriever("Hematology KB")
    uc = LabAnalysisUseCase(
        llm=groq,
        gemini=FakeGeminiClient(),
        clinical=FakeClinicalClient(),
        retriever=retriever,
    )

    await uc.execute(_lab_request())

    assert retriever.call_count == 1


@pytest.mark.asyncio
async def test_lab_analysis_without_retriever_still_works():
    from Application.lab_analysis import LabAnalysisUseCase

    groq = FakeGroqCompleter()
    uc = LabAnalysisUseCase(
        llm=groq,
        gemini=FakeGeminiClient(),
        clinical=FakeClinicalClient(),
        retriever=None,
    )

    result = await uc.execute(_lab_request())
    assert result.draft_text == "Draft report"


@pytest.mark.asyncio
async def test_lab_analysis_retriever_passed_department():
    from Application.lab_analysis import LabAnalysisUseCase

    retriever = FakeRetriever()
    uc = LabAnalysisUseCase(
        llm=FakeGroqCompleter(),
        gemini=FakeGeminiClient(),
        clinical=FakeClinicalClient(),
        retriever=retriever,
    )

    await uc.execute(_lab_request(department=Department.ENDOCRINOLOGY))

    assert retriever.last_department == "endocrinology"


@pytest.mark.asyncio
async def test_lab_analysis_rag_context_in_user_prompt():
    from Application.lab_analysis import LabAnalysisUseCase

    groq = FakeGroqCompleter()
    retriever = FakeRetriever(
        "── KNOWLEDGE BASE CONTEXT ──\nHematology reference ranges\n── END CONTEXT ──"
    )
    uc = LabAnalysisUseCase(
        llm=groq,
        gemini=FakeGeminiClient(),
        clinical=FakeClinicalClient(),
        retriever=retriever,
    )

    await uc.execute(_lab_request())

    assert "Hematology reference ranges" in groq.last_user_prompt


# ---------------------------------------------------------------------------
# EmrSummaryUseCase
# ---------------------------------------------------------------------------

def _emr_request(diagnoses=None):
    return EmrSummaryRequest(
        patient_id="p-emr-001",
        doctor_id="doc-001",
        language="vi",
    )


@pytest.mark.asyncio
async def test_emr_summary_calls_retriever_with_diagnoses():
    from Application.emr_summary import EmrSummaryUseCase

    groq = FakeGroqStreamer()
    retriever = FakeRetriever("Hypertension management guidelines")
    uc = EmrSummaryUseCase(
        llm=groq,
        clinical=FakeClinicalClient(diagnoses=["Hypertension", "T2DM"]),
        emr_result=FakeEmrResultClient(),
        retriever=retriever,
    )

    req = _emr_request()
    async for _ in uc.execute(req, token="tok-abc", x_user_id="doc-1", x_user_role="doctor"):
        pass

    assert retriever.call_count == 1
    # Query must be derived from active_diagnoses
    assert "Hypertension" in retriever.last_query or "T2DM" in retriever.last_query


@pytest.mark.asyncio
async def test_emr_summary_without_retriever_still_works():
    from Application.emr_summary import EmrSummaryUseCase

    groq = FakeGroqStreamer(["Summary text"])
    uc = EmrSummaryUseCase(
        llm=groq,
        clinical=FakeClinicalClient(),
        emr_result=FakeEmrResultClient(),
        retriever=None,
    )

    req = _emr_request()
    chunks = []
    async for c in uc.execute(req, token="tok-xyz", x_user_id="doc-1", x_user_role="doctor"):
        chunks.append(c)

    assert len(chunks) > 0


@pytest.mark.asyncio
async def test_emr_summary_rag_context_in_user_prompt():
    from Application.emr_summary import EmrSummaryUseCase

    groq = FakeGroqStreamer()
    retriever = FakeRetriever(
        "── KNOWLEDGE BASE CONTEXT ──\nCKD management KDIGO\n── END CONTEXT ──"
    )
    uc = EmrSummaryUseCase(
        llm=groq,
        clinical=FakeClinicalClient(diagnoses=["CKD Stage 3"]),
        emr_result=FakeEmrResultClient(),
        retriever=retriever,
    )

    req = _emr_request()
    async for _ in uc.execute(req, token="tok", x_user_id="doc-1", x_user_role="doctor"):
        pass

    assert "KDIGO" in groq.last_user_prompt or "CKD management" in groq.last_user_prompt



