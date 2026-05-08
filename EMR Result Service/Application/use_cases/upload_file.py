from dataclasses import dataclass
from pathlib import Path

from Application.dtos import FileUploadResponse
from Domain.interfaces.file_storage import IFileStorage


# MIME type → normalised file_type string
_MIME_TO_TYPE: dict[str, str] = {
    "application/pdf": "pdf",
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
}

# File extension fallback (browser MIME can be unreliable for binary uploads)
_EXT_TO_TYPE: dict[str, str] = {
    ".pdf": "pdf",
    ".png": "png",
    ".jpg": "jpg",
    ".jpeg": "jpeg",
    ".dcm": "dicom",
    ".dicom": "dicom",
}

# MIME prefixes that must never be accepted
_BLOCKED_MIME_PREFIXES = (
    "text/html",
    "text/javascript",
    "application/javascript",
    "application/x-sh",
    "application/x-executable",
    "application/x-msdownload",
)


@dataclass
class UploadFileRequest:
    data: bytes
    original_filename: str
    content_type: str
    subfolder: str = "lab_results"


class UploadFileUseCase:
    """Handle file validation and storage for the POST /upload endpoint."""

    def __init__(self, storage: IFileStorage, max_bytes: int) -> None:
        self._storage = storage
        self._max_bytes = max_bytes

    def execute(self, request: UploadFileRequest) -> FileUploadResponse:
        content_type = request.content_type.lower()

        if any(content_type.startswith(p) for p in _BLOCKED_MIME_PREFIXES):
            raise ValueError(f"unsupported_mime:{content_type}")

        if not request.data:
            raise ValueError("empty_file")

        if len(request.data) > self._max_bytes:
            limit_mb = self._max_bytes // (1024 * 1024)
            raise ValueError(f"size_exceeded:{limit_mb}")

        ext = Path(request.original_filename).suffix.lower()
        file_type = _MIME_TO_TYPE.get(content_type) or _EXT_TO_TYPE.get(ext, "other")

        url, size = self._storage.save(
            request.data, request.original_filename, request.subfolder
        )

        return FileUploadResponse(
            url=url,
            file_type=file_type,
            original_filename=request.original_filename,
            size_bytes=size,
        )
