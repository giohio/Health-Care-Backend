import asyncio
import pytest
from Application.lab_analysis import LabAnalysisUseCase
from Domain.entities import LabAnalysisRequest, PatientContext
from Domain.enums import InputType, Department


async def _yield_control():
    await asyncio.sleep(0)


class FakeGroqClient:
    def __init__(self, text="Draft lâm sàng"):
        self.last_user_prompt = None
        self._text = text

    async def complete(self, system_prompt, user_prompt, **kwargs):
        self.last_user_prompt = user_prompt
        await _yield_control()
        return self._text


class FakeGeminiClient:
    def __init__(self, findings=None, fail=False):
        self.extract_findings_called = False
        self.extract_tabular_called  = False
        self._findings = findings or {"confidence": 0.85, "keywords": ["normal"]}
        self._fail     = fail

    async def extract_findings(self, image_bytes, mime_type, test_type, **kwargs):
        self.extract_findings_called = True
        await _yield_control()
        if self._fail:
            return {"error": "vision_parse_failed", "raw": "bad json"}
        return self._findings

    async def extract_tabular(self, tabular_data, test_type):
        self.extract_tabular_called = True
        await _yield_control()
        if self._fail:
            return {"error": "vision_parse_failed", "raw": "bad json"}
        return self._findings


class FakeClinicalClient:
    async def get_patient_context(self, patient_id, x_user_id, x_user_role):
        await _yield_control()
        return PatientContext(
            patient_id=patient_id,
            full_name="Bệnh nhân",
            age=None,
            gender=None,
        )


@pytest.mark.asyncio
async def test_lab_analysis_tabular_path_skips_image_download():
    groq    = FakeGroqClient()
    gemini  = FakeGeminiClient()
    use_case = LabAnalysisUseCase(llm=groq, gemini=gemini, clinical=FakeClinicalClient())

    request = LabAnalysisRequest(
        result_id    = "r-001",
        patient_id   = "p-001",
        file_url     = "http://example.com/result.pdf",
        input_type   = InputType.TABULAR,
        department   = Department.HEMATOLOGY,
        test_name    = "CBC",
        tabular_data = {"WBC": 5.0, "RBC": 4.5},
    )

    result = await use_case.execute(request)

    assert gemini.extract_tabular_called is True
    assert gemini.extract_findings_called is False
    assert result.result_id == "r-001"
    assert result.confidence == pytest.approx(0.85)
    assert "text" in result.model_versions
    assert "vision" in result.model_versions


@pytest.mark.asyncio
async def test_lab_analysis_failed_vision_returns_manual_review():
    groq    = FakeGroqClient()
    gemini  = FakeGeminiClient(fail=True)
    use_case = LabAnalysisUseCase(llm=groq, gemini=gemini, clinical=FakeClinicalClient())

    # Use TABULAR path so no HTTP download is attempted; the FakeGeminiClient returns an error dict
    request = LabAnalysisRequest(
        result_id    = "r-002",
        patient_id   = "p-001",
        file_url     = "",
        input_type   = InputType.TABULAR,
        department   = Department.RESPIRATORY,
        test_name    = "X-quang ngực",
        tabular_data = {"placeholder": True},
    )

    result = await use_case.execute(request)

    assert result.visual_findings is None
    assert result.confidence == pytest.approx(0.0)
    assert result.requires_specialist_review is True
    assert "manual review" in result.draft_text.lower()


@pytest.mark.asyncio
async def test_lab_analysis_result_contains_groq_draft():
    draft  = "⚠️ ĐÂY LÀ BẢN NHÁP AI"
    groq   = FakeGroqClient(text=draft)
    gemini = FakeGeminiClient()
    use_case = LabAnalysisUseCase(llm=groq, gemini=gemini, clinical=FakeClinicalClient())

    request = LabAnalysisRequest(
        result_id    = "r-003",
        patient_id   = "p-001",
        file_url     = "",
        input_type   = InputType.TABULAR,
        department   = Department.ENDOCRINOLOGY,
        test_name    = "Thyroid panel",
        tabular_data = {"TSH": 2.1},
    )

    result = await use_case.execute(request)

    assert result.draft_text == draft


@pytest.mark.asyncio
async def test_lab_analysis_test_name_in_synthesis_prompt():
    groq   = FakeGroqClient()
    gemini = FakeGeminiClient()
    use_case = LabAnalysisUseCase(llm=groq, gemini=gemini, clinical=FakeClinicalClient())

    request = LabAnalysisRequest(
        result_id    = "r-004",
        patient_id   = "p-001",
        file_url     = "",
        input_type   = InputType.TABULAR,
        department   = Department.NEPHROLOGY,
        test_name    = "Creatinine & eGFR",
        tabular_data = {"creatinine": 1.2},
    )

    await use_case.execute(request)

    assert "Creatinine & eGFR" in groq.last_user_prompt


# ---------------------------------------------------------------------------
# File download failure fallback tests (X-ray / image upload scenarios)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_lab_analysis_download_failure_returns_manual_review():
    """When file download fails (e.g. unreachable URL), return manual-review result instead of crashing."""
    groq    = FakeGroqClient()
    gemini  = FakeGeminiClient()
    use_case = LabAnalysisUseCase(llm=groq, gemini=gemini, clinical=FakeClinicalClient())

    request = LabAnalysisRequest(
        result_id    = "r-xray-001",
        patient_id   = "p-001",
        file_url     = "http://emr_result_service:8000/uploads/lab_results/xray.jpg",
        input_type   = InputType.IMAGE,
        department   = Department.RESPIRATORY,
        test_name    = "Chest X-Ray",
        tabular_data = None,
    )

    from unittest.mock import AsyncMock, patch
    import httpx

    with patch.object(
        use_case,
        "_download_file",
        new=AsyncMock(side_effect=httpx.ConnectError("Name or service not known")),
    ):
        result = await use_case.execute(request)

    # Should NOT crash; returns a manual-review result
    assert result.result_id == "r-xray-001"
    assert result.requires_specialist_review is True
    assert result.confidence == pytest.approx(0.0)
    assert "manual" in result.draft_text.lower() or "unable" in result.draft_text.lower()
    # Vision extraction should not be called
    assert gemini.extract_findings_called is False


@pytest.mark.asyncio
async def test_lab_analysis_download_failure_does_not_call_gemini_vision():
    """Vision client must not be called when the file cannot be downloaded."""
    groq    = FakeGroqClient()
    gemini  = FakeGeminiClient()
    use_case = LabAnalysisUseCase(llm=groq, gemini=gemini, clinical=FakeClinicalClient())

    request = LabAnalysisRequest(
        result_id    = "r-xray-002",
        patient_id   = "p-001",
        file_url     = "http://unreachable-host/file.png",
        input_type   = InputType.IMAGE,
        department   = Department.RADIOLOGY,
        test_name    = "Abdominal X-Ray",
        tabular_data = None,
    )

    from unittest.mock import AsyncMock, patch
    import httpx

    with patch.object(
        use_case,
        "_download_file",
        new=AsyncMock(side_effect=httpx.TimeoutException("timeout")),
    ):
        result = await use_case.execute(request)

    assert gemini.extract_findings_called is False
    assert result.requires_specialist_review is True


@pytest.mark.asyncio
async def test_lab_analysis_successful_xray_calls_gemini_vision():
    """When download succeeds, Gemini vision extraction IS called for image input."""
    groq    = FakeGroqClient()
    gemini  = FakeGeminiClient(findings={"confidence": 0.92, "keywords": ["infiltrate"]})
    use_case = LabAnalysisUseCase(llm=groq, gemini=gemini, clinical=FakeClinicalClient())

    request = LabAnalysisRequest(
        result_id    = "r-xray-003",
        patient_id   = "p-001",
        file_url     = "http://emr_result_service:8000/uploads/lab_results/xray.jpg",
        input_type   = InputType.IMAGE,
        department   = Department.RESPIRATORY,
        test_name    = "Chest X-Ray",
        tabular_data = None,
    )

    from unittest.mock import AsyncMock, patch

    with patch.object(
        use_case,
        "_download_file",
        new=AsyncMock(return_value=b"\xff\xd8\xff" + b"\x00" * 100),  # fake JPEG bytes
    ):
        result = await use_case.execute(request)

    assert gemini.extract_findings_called is True
    assert result.result_id == "r-xray-003"
    assert result.confidence == pytest.approx(0.92)

