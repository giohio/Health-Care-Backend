from typing import Any

from infrastructure.repositories.system_settings_repository import SystemSettingsRepository


class GetNotificationSettingsUseCase:
    def __init__(self, settings_repo: SystemSettingsRepository):
        self.settings_repo = settings_repo

    async def execute(self) -> dict[str, Any]:
        cfg = await self.settings_repo.get()
        return {
            "settings": cfg.notification_settings,
            "updated_at": cfg.updated_at.isoformat() if cfg.updated_at else None,
            "updated_by": str(cfg.updated_by) if cfg.updated_by else None,
        }
