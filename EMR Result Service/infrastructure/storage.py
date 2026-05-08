import uuid
from pathlib import Path

from Domain.interfaces.file_storage import IFileStorage


class LocalFileStorage(IFileStorage):
    """Saves files to a local directory and returns a public URL."""

    def __init__(self, upload_dir: str, base_url: str) -> None:
        self._dir = Path(upload_dir)
        self._base_url = base_url.rstrip("/")

    def save(self, data: bytes, original_filename: str, subfolder: str = "") -> tuple[str, int]:
        """Write *data* to disk. Returns ``(public_url, size_bytes)``."""
        ext = Path(original_filename).suffix.lower()
        unique_name = f"{uuid.uuid4().hex}{ext}"
        target_dir = self._dir / subfolder if subfolder else self._dir
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / unique_name).write_bytes(data)
        url_path = f"{subfolder}/{unique_name}" if subfolder else unique_name
        return f"{self._base_url}/{url_path}", len(data)
