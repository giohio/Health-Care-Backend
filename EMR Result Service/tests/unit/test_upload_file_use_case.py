"""Unit tests for UploadFileUseCase — covers Application/use_cases/upload_file.py."""
import pytest

from Application.dtos import FileUploadResponse
from Application.use_cases.upload_file import UploadFileRequest, UploadFileUseCase
from Domain.interfaces.file_storage import IFileStorage


class FakeStorage(IFileStorage):
    """In-memory stub — returns predictable URL and the byte length."""

    def save(self, data: bytes, original_filename: str, subfolder: str = "") -> tuple[str, int]:
        folder = f"{subfolder}/" if subfolder else ""
        return (f"http://storage/{folder}{original_filename}", len(data))


def make_use_case(max_bytes: int = 10 * 1024 * 1024) -> UploadFileUseCase:
    return UploadFileUseCase(storage=FakeStorage(), max_bytes=max_bytes)


class TestBlockedMimeTypes:
    def test_html_mime_raises(self):
        uc = make_use_case()
        req = UploadFileRequest(data=b"<html>", original_filename="x.html", content_type="text/html")
        with pytest.raises(ValueError) as exc_info:
            uc.execute(req)
        assert "unsupported_mime:text/html" in str(exc_info.value)

    def test_javascript_mime_raises(self):
        uc = make_use_case()
        req = UploadFileRequest(data=b"alert(1)", original_filename="s.js", content_type="text/javascript")
        with pytest.raises(ValueError) as exc_info:
            uc.execute(req)
        assert "unsupported_mime" in str(exc_info.value)

    def test_application_javascript_mime_raises(self):
        uc = make_use_case()
        req = UploadFileRequest(
            data=b"code",
            original_filename="s.js",
            content_type="application/javascript",
        )
        with pytest.raises(ValueError) as exc_info:
            uc.execute(req)
        assert "unsupported_mime" in str(exc_info.value)

    def test_shell_script_mime_raises(self):
        uc = make_use_case()
        req = UploadFileRequest(data=b"#!/bin/sh", original_filename="s.sh", content_type="application/x-sh")
        with pytest.raises(ValueError) as exc_info:
            uc.execute(req)
        assert "unsupported_mime" in str(exc_info.value)

    def test_executable_mime_raises(self):
        uc = make_use_case()
        req = UploadFileRequest(
            data=b"\x4D\x5A",
            original_filename="prog.exe",
            content_type="application/x-msdownload",
        )
        with pytest.raises(ValueError) as exc_info:
            uc.execute(req)
        assert "unsupported_mime" in str(exc_info.value)


class TestEmptyAndSizeValidation:
    def test_empty_bytes_raises(self):
        uc = make_use_case()
        req = UploadFileRequest(data=b"", original_filename="empty.pdf", content_type="application/pdf")
        with pytest.raises(ValueError) as exc_info:
            uc.execute(req)
        assert str(exc_info.value) == "empty_file"

    def test_file_exceeds_limit_raises(self):
        uc = make_use_case(max_bytes=1024)  # 1 KB limit
        req = UploadFileRequest(
            data=b"x" * 2000,
            original_filename="big.pdf",
            content_type="application/pdf",
        )
        with pytest.raises(ValueError) as exc_info:
            uc.execute(req)
        assert "size_exceeded" in str(exc_info.value)

    def test_size_exceeded_message_contains_mb_limit(self):
        uc = make_use_case(max_bytes=5 * 1024 * 1024)  # 5 MB
        req = UploadFileRequest(
            data=b"x" * (6 * 1024 * 1024),
            original_filename="huge.pdf",
            content_type="application/pdf",
        )
        with pytest.raises(ValueError) as exc_info:
            uc.execute(req)
        assert "size_exceeded:5" in str(exc_info.value)

    def test_file_exactly_at_limit_is_accepted(self):
        uc = make_use_case(max_bytes=1024)
        req = UploadFileRequest(
            data=b"x" * 1024,
            original_filename="ok.pdf",
            content_type="application/pdf",
        )
        resp = uc.execute(req)
        assert resp.size_bytes == 1024


class TestFileTypeResolution:
    def test_pdf_by_mime(self):
        uc = make_use_case()
        req = UploadFileRequest(data=b"%PDF", original_filename="r.pdf", content_type="application/pdf")
        resp = uc.execute(req)
        assert resp.file_type == "pdf"

    def test_png_by_mime(self):
        uc = make_use_case()
        req = UploadFileRequest(data=b"\x89PNG", original_filename="x.png", content_type="image/png")
        resp = uc.execute(req)
        assert resp.file_type == "png"

    def test_jpeg_by_mime(self):
        uc = make_use_case()
        req = UploadFileRequest(data=b"\xFF\xD8", original_filename="s.jpg", content_type="image/jpeg")
        resp = uc.execute(req)
        assert resp.file_type == "jpg"

    def test_image_jpg_content_type(self):
        uc = make_use_case()
        req = UploadFileRequest(data=b"\xFF\xD8", original_filename="s.jpg", content_type="image/jpg")
        resp = uc.execute(req)
        assert resp.file_type == "jpg"

    def test_dicom_by_extension_fallback(self):
        uc = make_use_case()
        req = UploadFileRequest(
            data=b"DICM",
            original_filename="scan.dcm",
            content_type="application/octet-stream",
        )
        resp = uc.execute(req)
        assert resp.file_type == "dicom"

    def test_dicom_long_extension(self):
        uc = make_use_case()
        req = UploadFileRequest(
            data=b"DICM",
            original_filename="scan.dicom",
            content_type="application/octet-stream",
        )
        resp = uc.execute(req)
        assert resp.file_type == "dicom"

    def test_unknown_extension_defaults_to_other(self):
        uc = make_use_case()
        req = UploadFileRequest(
            data=b"binary",
            original_filename="data.xyz",
            content_type="application/octet-stream",
        )
        resp = uc.execute(req)
        assert resp.file_type == "other"


class TestResponseFields:
    def test_returns_file_upload_response(self):
        uc = make_use_case()
        req = UploadFileRequest(data=b"%PDF", original_filename="result.pdf", content_type="application/pdf")
        resp = uc.execute(req)
        assert isinstance(resp, FileUploadResponse)

    def test_url_not_empty(self):
        uc = make_use_case()
        req = UploadFileRequest(data=b"%PDF", original_filename="result.pdf", content_type="application/pdf")
        resp = uc.execute(req)
        assert resp.url != ""

    def test_original_filename_preserved(self):
        uc = make_use_case()
        req = UploadFileRequest(data=b"%PDF", original_filename="my_result.pdf", content_type="application/pdf")
        resp = uc.execute(req)
        assert resp.original_filename == "my_result.pdf"

    def test_size_bytes_matches_data_length(self):
        uc = make_use_case()
        data = b"hello world PDF content"
        req = UploadFileRequest(data=data, original_filename="r.pdf", content_type="application/pdf")
        resp = uc.execute(req)
        assert resp.size_bytes == len(data)

    def test_custom_subfolder_used(self):
        uc = make_use_case()
        req = UploadFileRequest(
            data=b"%PDF",
            original_filename="r.pdf",
            content_type="application/pdf",
            subfolder="radiology",
        )
        resp = uc.execute(req)
        assert resp.url is not None
