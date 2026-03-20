from uuid_extension import uuid7, UUID7
from datetime import datetime, timezone


def new_id() -> UUID7:
    """Tạo UUID7 mới. Dùng thay uuid4() ở mọi chỗ."""
    return uuid7()


def extract_timestamp(uid) -> datetime:
    """
    Extract created_at từ UUID7.
    Không cần query DB để biết thời điểm tạo.
    """
    if isinstance(uid, str):
        uid = UUID7(uid)
    ts_ms = uid.int >> 80
    return datetime.fromtimestamp(
        ts_ms / 1000, tz=timezone.utc
    )
