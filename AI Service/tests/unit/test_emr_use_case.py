import asyncio
import pytest
from Application.emr_summary import EmrSummaryUseCase
from Domain.entities import EmrSummaryRequest, PatientContext


async def _yield_control():
    await asyncio.sleep(0)


class FakeGroqClient:
    def __init__(self, chunks=None):
        self.last_system_prompt = None
        self.last_user_prompt   = None
        self._chunks = chunks or ["Tóm tắt EMR: ", "Bệnh nhân ổn định."]

    async def stream_completion(self, system_prompt, user_prompt, **kwargs):
        self.last_system_prompt = system_prompt
        self.last_user_prompt   = user_prompt
        await _yield_control()
        for chunk in self._chunks:
            yield chunk


class FakeClinicalClient:
    def __init__(self, context=None):
        self._context = context or PatientContext(
            patient_id="p-001",
            full_name="Phạm Thị D",
            age=60,
            gender="female",
            active_diagnoses=["Suy tim độ 2"],
            current_medications=["Furosemide 40mg"],
            allergies="",
            chronic_conditions="",
        )

    async def get_patient_context(self, patient_id, x_user_id, x_user_role):
        await _yield_control()
        return self._context


class FakeEmrResultClient:
    def __init__(self, results=None):
        self.called = False
        self._results = results or [
            {"test_name": "Điện tâm đồ", "summary": "Nhịp xoang bình thường"},
        ]

    async def get_recent_results(self, patient_id, token, x_user_id, x_user_role, limit=5):
        self.called = True
        await _yield_control()
        return self._results


@pytest.mark.asyncio
async def test_emr_summary_yields_all_chunks():
    use_case = EmrSummaryUseCase(
        llm=FakeGroqClient(["chunk A", "chunk B"]),
        clinical=FakeClinicalClient(),
        emr_result=FakeEmrResultClient(),
    )

    request = EmrSummaryRequest(patient_id="p-001", doctor_id="d-001")
    chunks  = [c async for c in use_case.execute(request, "token-x", "d-001", "doctor")]

    assert chunks == ["chunk A", "chunk B"]


@pytest.mark.asyncio
async def test_emr_summary_fetches_recent_labs():
    emr_client = FakeEmrResultClient()
    use_case   = EmrSummaryUseCase(
        llm=FakeGroqClient(),
        clinical=FakeClinicalClient(),
        emr_result=emr_client,
    )

    request = EmrSummaryRequest(patient_id="p-001", doctor_id="d-001")
    async for _ in use_case.execute(request, "token-y", "d-001", "doctor"):
        ...  # exhaust the generator to trigger side effects

    assert emr_client.called is True


@pytest.mark.asyncio
async def test_emr_summary_prompt_includes_patient_and_labs():
    context = PatientContext(
        patient_id="p-001",
        full_name="Ngô Văn E",
        age=35,
        gender="male",
        active_diagnoses=[],
        current_medications=[],
        allergies="",
        chronic_conditions="",
    )
    labs = [{"test_name": "Siêu âm bụng", "summary": "Gan bình thường"}]
    groq = FakeGroqClient()

    use_case = EmrSummaryUseCase(
        llm=groq,
        clinical=FakeClinicalClient(context=context),
        emr_result=FakeEmrResultClient(results=labs),
    )

    request = EmrSummaryRequest(patient_id="p-001", doctor_id="d-001")
    async for _ in use_case.execute(request, "token", "d-001", "doctor"):
        ...  # exhaust the generator; assertions follow

    assert "Ngô Văn E" in groq.last_user_prompt
    assert "Siêu âm bụng" in groq.last_user_prompt


@pytest.mark.asyncio
async def test_emr_summary_with_no_labs_does_not_crash():
    use_case = EmrSummaryUseCase(
        llm=FakeGroqClient(),
        clinical=FakeClinicalClient(),
        emr_result=FakeEmrResultClient(results=[]),
    )

    request = EmrSummaryRequest(patient_id="p-001", doctor_id="d-001")
    chunks  = [c async for c in use_case.execute(request, "token", "d-001", "doctor")]

    assert len(chunks) > 0


