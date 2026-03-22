from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, BeforeValidator
from typing_extensions import Annotated


def coerce_to_uuid_str(v: Any) -> Any:
    if hasattr(v, "__class__") and v.__class__.__name__ == "UUID7":
        return str(v)
    return v


SafeUUID = Annotated[UUID, BeforeValidator(coerce_to_uuid_str)]


class NotificationResponse(BaseModel):
    id: SafeUUID
    user_id: SafeUUID
    title: str
    body: str
    event_type: str
    is_read: bool
    created_at: datetime | None = None
    read_at: datetime | None = None

    class Config:
        from_attributes = True
