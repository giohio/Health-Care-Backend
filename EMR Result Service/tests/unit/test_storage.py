"""Unit tests for LocalFileStorage — covers infrastructure/storage.py."""
import pytest

from infrastructure.storage import LocalFileStorage


class TestLocalFileStorage:
    def test_save_returns_url_and_size(self, tmp_path):
        storage = LocalFileStorage(upload_dir=str(tmp_path), base_url="http://localhost:8080")
        data = b"test file content"
        url, size = storage.save(data, "result.pdf", subfolder="lab_results")
        assert size == len(data)
        assert url.startswith("http://localhost:8080/lab_results/")
        assert url.endswith(".pdf")

    def test_save_creates_subfolder(self, tmp_path):
        storage = LocalFileStorage(upload_dir=str(tmp_path), base_url="http://storage")
        storage.save(b"data", "file.png", subfolder="images/radiology")
        subfolder = tmp_path / "images" / "radiology"
        assert subfolder.exists()
        assert subfolder.is_dir()

    def test_save_without_subfolder(self, tmp_path):
        storage = LocalFileStorage(upload_dir=str(tmp_path), base_url="http://storage")
        data = b"binary content"
        url, size = storage.save(data, "scan.dcm", subfolder="")
        assert size == len(data)
        assert url.startswith("http://storage/")
        assert url.endswith(".dcm")

    def test_file_is_written_to_disk(self, tmp_path):
        storage = LocalFileStorage(upload_dir=str(tmp_path), base_url="http://storage")
        data = b"important data"
        url, _ = storage.save(data, "report.pdf", subfolder="reports")
        # Derive filename from URL to check the file exists
        filename = url.split("/")[-1]
        written_file = tmp_path / "reports" / filename
        assert written_file.exists()
        assert written_file.read_bytes() == data

    def test_unique_filenames_for_same_input(self, tmp_path):
        storage = LocalFileStorage(upload_dir=str(tmp_path), base_url="http://storage")
        data = b"some data"
        url1, _ = storage.save(data, "result.pdf", subfolder="lab")
        url2, _ = storage.save(data, "result.pdf", subfolder="lab")
        assert url1 != url2

    def test_base_url_trailing_slash_stripped(self, tmp_path):
        storage = LocalFileStorage(upload_dir=str(tmp_path), base_url="http://storage/")
        url, _ = storage.save(b"data", "file.pdf", subfolder="lab")
        assert "http://storage//lab" not in url
        assert url.startswith("http://storage/lab")

    def test_size_is_exact_byte_length(self, tmp_path):
        storage = LocalFileStorage(upload_dir=str(tmp_path), base_url="http://storage")
        data = b"\x00" * 512
        _, size = storage.save(data, "blank.pdf", subfolder="test")
        assert size == 512
