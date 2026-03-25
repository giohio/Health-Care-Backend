from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, BeforeValidator, ConfigDict, computed_field
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

    @computed_field
    def type(self) -> str:
        # Keep backward-compatible high-level type used by E2E filters.
        if "." in self.event_type:
            return self.event_type.split(".", 1)[0]
        return self.event_type

    model_config = ConfigDict(from_attributes=True)


class NotificationListResponse(BaseModel):
    notifications: list[NotificationResponse]
    unread_count: int
