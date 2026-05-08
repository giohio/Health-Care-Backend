"""
Unit tests covering Application/lab_analysis.py branches not reached by the
tabular-path tests:

  - Image download path (lines 55-57)
  - _download_file (lines 99-102)
  - _detect_mime (lines 106-113)
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from Application.lab_analysis import LabAnalysisUseCase, DEPT_TO_VISION_KEY
from Domain.entities import LabAnalysisRequest, PatientContext
from Domain.enums import InputType, Department


# ---------------------------------------------------------------------------
# Shared Fake helpers (mirrors those in test_lab_use_case.py)
# ---------------------------------------------------------------------------

class FakeGroqClient:
    async def complete(self, system_prompt, user_prompt, **kwargs):
        await asyncio.sleep(0)
        return "Kết quả phân tích tổng hợp bởi AI."


class FakeGeminiClient:
    def __init__(self, findings=None, fail=False):
        self._findings = findings or {"impression": "normal", "confidence": 0.82}
        self._fail = fail

    async def extract_findings(self, image_bytes, mime_type, test_type, **kwargs):
        await asyncio.sleep(0)
        if self._fail:
            return {"error": "vision_parse_failed", "raw": ""}
        return self._findings

    async def extract_tabular(self, tabular_data, test_type):
        await asyncio.sleep(0)
        return self._findings


class FakeClinicalClient:
    async def get_patient_context(self, patient_id, x_user_id, x_user_role):
        await asyncio.sleep(0)
        return PatientContext(
            patient_id=patient_id,
            full_name="Bệnh nhân",
            age=40,
            gender="male",
        )


# ---------------------------------------------------------------------------
# _detect_mime tests
# ---------------------------------------------------------------------------

def test_detect_mime_jpg():
    assert LabAnalysisUseCase._detect_mime("http://host/image.jpg") == "image/jpeg"


def test_detect_mime_jpeg():
    assert LabAnalysisUseCase._detect_mime("scan.JPEG") == "image/jpeg"


def test_detect_mime_png():
    assert LabAnalysisUseCase._detect_mime("http://host/scan.png") == "image/png"


def test_detect_mime_dicom():
    assert LabAnalysisUseCase._detect_mime("study.dicom") == "image/jpeg"


def test_detect_mime_dcm():
    assert LabAnalysisUseCase._detect_mime("/path/to/file.dcm") == "image/jpeg"


def test_detect_mime_unknown_defaults_to_jpeg():
    assert LabAnalysisUseCase._detect_mime("report.pdf") == "image/jpeg"


# ---------------------------------------------------------------------------
# DEPT_TO_VISION_KEY mapping tests
# ---------------------------------------------------------------------------

def test_dept_to_vision_key_all_departments():
    expected = {
        "respiratory":      "chest_xray",
        "cardiology":       "ecg",
        "dermatology":      "skin_lesion",
        "neurology":        "brain_mri",
        "ophthalmology":    "fundus",
        "hematology":       "blood_panel",
        "nephrology":       "blood_panel",
        "endocrinology":    "blood_panel",
        "internal_medicine": "abdominal_xray",
        "radiology":        "bone_xray",
    }
    for dept, key in expected.items():
        assert DEPT_TO_VISION_KEY.get(dept) == key


def test_dept_to_vision_key_unknown_defaults_blood_panel():
    assert DEPT_TO_VISION_KEY.get("unknown_dept", "blood_panel") == "blood_panel"


# ---------------------------------------------------------------------------
# Image download path tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_lab_image_path_calls_download_and_extract_findings():
    """Input type IMAGE → _download_file → gemini.extract_findings."""
    fake_bytes = b"fake-xray-image-content"

    fake_gemini = FakeGeminiClient(findings={"impression": "Opacification noted", "confidence": 0.91})

    # Patch _download_file at the class level to return fake bytes
    with patch.object(LabAnalysisUseCase, "_download_file", new_callable=AsyncMock) as mock_download:
        mock_download.return_value = fake_bytes

        use_case = LabAnalysisUseCase(
            llm=FakeGroqClient(),
            gemini=fake_gemini,
            clinical=FakeClinicalClient(),
        )
        request = LabAnalysisRequest(
            result_id="r-scan-001",
            patient_id="p-001",
            file_url="https://storage.service/xray.png",
            input_type=InputType.IMAGE,
            department=Department.RESPIRATORY,
            test_name="Chest X-Ray",
        )
        result = await use_case.execute(request)

    mock_download.assert_called_once_with("https://storage.service/xray.png")
    assert result.result_id == "r-scan-001"
    assert result.confidence == pytest.approx(0.91)
    assert result.visual_findings["impression"] == "Opacification noted"


@pytest.mark.asyncio
async def test_lab_image_path_failed_vision_returns_manual_review():
    """Gemini vision failure on IMAGE path → manual review response."""
    with patch.object(LabAnalysisUseCase, "_download_file", new_callable=AsyncMock) as mock_dl:
        mock_dl.return_value = b"corrupted-bytes"

        use_case = LabAnalysisUseCase(
            llm=FakeGroqClient(),
            gemini=FakeGeminiClient(fail=True),
            clinical=FakeClinicalClient(),
        )
        request = LabAnalysisRequest(
            result_id="r-scan-002",
            patient_id="p-002",
            file_url="https://storage.service/bad.jpg",
            input_type=InputType.IMAGE,
            department=Department.CARDIOLOGY,
            test_name="ECG",
        )
        result = await use_case.execute(request)

    assert result.visual_findings is None
    assert result.confidence == pytest.approx(0.0)
    assert "Cần xem xét thủ công" in result.draft_text


@pytest.mark.asyncio
async def test_download_file_makes_get_request():
    """_download_file issues a GET and returns response content."""
    fake_response = MagicMock()
    fake_response.raise_for_status = MagicMock()
    fake_response.content = b"image-bytes-content"

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get = AsyncMock(return_value=fake_response)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await LabAnalysisUseCase._download_file("http://example.com/image.jpg")

    assert result == b"image-bytes-content"
    mock_client.get.assert_called_once_with("http://example.com/image.jpg")


