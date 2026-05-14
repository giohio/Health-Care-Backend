"""
Unit tests for Application/all_labs_analysis.py — AllLabsAnalysisUseCase
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock

from Application.all_labs_analysis import AllLabsAnalysisUseCase
from Domain.entities import AllLabsAnalysisRequest, AllLabsAnalysisResult, PatientContext


# ---------------------------------------------------------------------------
# Helpers / Fakes
# ---------------------------------------------------------------------------

def _make_request(results=None, **kwargs) -> AllLabsAnalysisRequest:
    defaults = dict(
        appointment_id="appt-001",
        patient_id="pat-001",
        summary_id="sum-001",
        results=results or [],
    )
    defaults.update(kwargs)
    return AllLabsAnalysisRequest(**defaults)


def _patient_context(**kwargs) -> PatientContext:
    defaults = dict(
        patient_id="pat-001",
        full_name="Nguyễn Văn A",
        age=45,
        gender="male",
        active_diagnoses=["Hypertension"],
        current_medications=["Amlodipine 5mg"],
        allergies="Penicillin",
        chronic_conditions="Diabetes type 2",
    )
    defaults.update(kwargs)
    return PatientContext(**defaults)


class FakeLLM:
    def __init__(self, response: str = "Holistic analysis text"):
        self.calls = []
        self._response = response

    async def complete(self, system_prompt=None, user_prompt=None, **kwargs):
        await asyncio.sleep(0)
        self.calls.append({"system": system_prompt, "user": user_prompt})
        return self._response


class FakeLLMFailing:
    async def complete(self, system_prompt=None, user_prompt=None, **kwargs):
        await asyncio.sleep(0)
        raise RuntimeError("LLM timeout")


class FakeClinical:
    def __init__(self, context=None, fail=False):
        self._context = context
        self._fail = fail

    async def get_patient_context(self, patient_id, x_user_id, x_user_role):
        await asyncio.sleep(0)
        if self._fail:
            raise RuntimeError("Clinical service unavailable")
        return self._context or _patient_context(patient_id=patient_id)


class FakeEmrClient:
    def __init__(self, published=None, fail=False):
        self._published = published or []
        self._fail = fail

    async def get_published_results_for_appointment(self, appointment_id, **kwargs):
        await asyncio.sleep(0)
        if self._fail:
            raise RuntimeError("EMR unavailable")
        return self._published

    async def patch_holistic_summary(self, *args, **kwargs):
        pass

    async def get_result(self, *args, **kwargs):
        return {}

    async def get_recent_results(self, *args, **kwargs):
        return []

    async def patch_ai_draft(self, *args, **kwargs):
        pass


_SAMPLE_RESULTS = [
    {
        "test_name": "CBC Panel",
        "ai_draft_text": "WBC 11.2 (high), RBC 4.1 (normal). Leukocytosis pattern.",
        "published_text": "Leukocytosis confirmed. No blast cells.",
        "ai_visual_findings": None,
    },
    {
        "test_name": "Chest X-Ray",
        "ai_draft_text": None,
        "published_text": "Right lower lobe consolidation suggestive of pneumonia.",
        "ai_visual_findings": '{"impression": "consolidation", "location": "RLL"}',
    },
]


# ---------------------------------------------------------------------------
# Success paths
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_returns_done_result_with_holistic_text():
    llm = FakeLLM("⚠️ AI HOLISTIC DRAFT — full analysis here")
    request = _make_request(results=_SAMPLE_RESULTS)

    use_case = AllLabsAnalysisUseCase(
        llm=llm,
        clinical=FakeClinical(),
        emr_client=FakeEmrClient(),
    )
    result = await use_case.execute(request)

    assert isinstance(result, AllLabsAnalysisResult)
    assert result.status == "DONE"
    assert result.summary_id == "sum-001"
    assert "AI HOLISTIC DRAFT" in result.holistic_text


@pytest.mark.asyncio
async def test_llm_receives_all_tests_in_prompt():
    """All test names must appear in the user prompt sent to the LLM."""
    llm = FakeLLM()
    request = _make_request(results=_SAMPLE_RESULTS)

    use_case = AllLabsAnalysisUseCase(
        llm=llm,
        clinical=FakeClinical(),
        emr_client=FakeEmrClient(),
    )
    await use_case.execute(request)

    assert len(llm.calls) == 1
    user_prompt = llm.calls[0]["user"]
    assert "CBC Panel" in user_prompt
    assert "Chest X-Ray" in user_prompt


@pytest.mark.asyncio
async def test_llm_receives_synthesis_system_prompt():
    """The LLM must be called with ALL_LABS_SYNTHESIS_SYSTEM."""
    llm = FakeLLM()
    request = _make_request(results=_SAMPLE_RESULTS)

    use_case = AllLabsAnalysisUseCase(
        llm=llm,
        clinical=FakeClinical(),
        emr_client=FakeEmrClient(),
    )
    await use_case.execute(request)

    system = llm.calls[0]["system"]
    assert "HOLISTIC" in system or "holistic" in system.lower()


@pytest.mark.asyncio
async def test_patient_context_included_in_prompt():
    """Patient name must appear in the user prompt."""
    llm = FakeLLM()
    ctx = _patient_context(full_name="Trần Thị B", age=60)
    request = _make_request(results=_SAMPLE_RESULTS)

    use_case = AllLabsAnalysisUseCase(
        llm=llm,
        clinical=FakeClinical(context=ctx),
        emr_client=FakeEmrClient(),
    )
    await use_case.execute(request)

    user_prompt = llm.calls[0]["user"]
    assert "Trần Thị B" in user_prompt


# ---------------------------------------------------------------------------
# Results fetched from EMR when request.results is empty
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fetches_published_results_when_request_has_none():
    """If request.results is empty, the use case fetches from EMR client."""
    llm = FakeLLM()
    emr = FakeEmrClient(published=_SAMPLE_RESULTS)
    request = _make_request(results=[])  # empty — must fetch from EMR

    use_case = AllLabsAnalysisUseCase(
        llm=llm,
        clinical=FakeClinical(),
        emr_client=emr,
    )
    result = await use_case.execute(request)

    assert result.status == "DONE"
    user_prompt = llm.calls[0]["user"]
    assert "CBC Panel" in user_prompt


# ---------------------------------------------------------------------------
# Failure / degraded paths
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_no_results_returns_failed_status():
    """With no results available, use case returns FAILED with a message."""
    llm = FakeLLM()
    emr = FakeEmrClient(published=[])
    request = _make_request(results=[])

    use_case = AllLabsAnalysisUseCase(
        llm=llm,
        clinical=FakeClinical(),
        emr_client=emr,
    )
    result = await use_case.execute(request)

    assert result.status == "FAILED"
    assert result.summary_id == "sum-001"
    assert result.holistic_text is not None
    # LLM should NOT have been called
    assert len(llm.calls) == 0


@pytest.mark.asyncio
async def test_llm_failure_returns_failed_status():
    """LLM errors cause FAILED status, must not propagate."""
    llm = FakeLLMFailing()
    request = _make_request(results=_SAMPLE_RESULTS)

    use_case = AllLabsAnalysisUseCase(
        llm=llm,
        clinical=FakeClinical(),
        emr_client=FakeEmrClient(),
    )
    result = await use_case.execute(request)

    assert result.status == "FAILED"
    assert result.holistic_text is not None


@pytest.mark.asyncio
async def test_clinical_failure_degrades_gracefully():
    """Clinical service failure must not abort the analysis — uses fallback context."""
    llm = FakeLLM()
    request = _make_request(results=_SAMPLE_RESULTS)

    use_case = AllLabsAnalysisUseCase(
        llm=llm,
        clinical=FakeClinical(fail=True),
        emr_client=FakeEmrClient(),
    )
    result = await use_case.execute(request)

    # Should still complete — clinical failure is non-fatal
    assert result.status == "DONE"
    assert len(llm.calls) == 1


@pytest.mark.asyncio
async def test_emr_fetch_failure_returns_failed():
    """EMR client failure with empty request results returns FAILED."""
    llm = FakeLLM()
    emr = FakeEmrClient(fail=True)
    request = _make_request(results=[])  # empty, EMR fetch will fail

    use_case = AllLabsAnalysisUseCase(
        llm=llm,
        clinical=FakeClinical(),
        emr_client=emr,
    )
    result = await use_case.execute(request)

    assert result.status == "FAILED"
    assert len(llm.calls) == 0


# ---------------------------------------------------------------------------
# summary_id passthrough
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_summary_id_passed_through_to_result():
    llm = FakeLLM("text")
    request = _make_request(results=_SAMPLE_RESULTS, summary_id="my-special-sum-id")

    use_case = AllLabsAnalysisUseCase(
        llm=llm,
        clinical=FakeClinical(),
        emr_client=FakeEmrClient(),
    )
    result = await use_case.execute(request)

    assert result.summary_id == "my-special-sum-id"
