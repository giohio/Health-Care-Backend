from dataclasses import dataclass
from datetime import datetime

from uuid_extension import UUID7


@dataclass
class Notification:
    id: UUID7
    user_id: UUID7
    title: str
    body: str
    event_type: str
    is_read: bool = False
    created_at: datetime | None = None
    read_at: datetime | None = None
