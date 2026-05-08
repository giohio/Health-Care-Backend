from typing import Any
from uuid import UUID

from infrastructure.repositories.system_settings_repository import SystemSettingsRepository


class UpsertNotificationSettingsUseCase:
    def __init__(self, settings_repo: SystemSettingsRepository):
        self.settings_repo = settings_repo

    async def execute(self, settings: list[dict], updated_by: UUID | None = None) -> dict[str, Any]:
        cfg = await self.settings_repo.upsert(
            notification_settings=settings,
            updated_by=updated_by,
        )
        return {
            "settings": cfg.notification_settings,
            "updated_at": cfg.updated_at.isoformat() if cfg.updated_at else None,
            "updated_by": str(cfg.updated_by) if cfg.updated_by else None,
        }
