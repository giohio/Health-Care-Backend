from typing import Any
from uuid import UUID

from infrastructure.repositories.system_settings_repository import SystemSettingsRepository


class UpsertSecuritySettingsUseCase:
    def __init__(self, settings_repo: SystemSettingsRepository):
        self.settings_repo = settings_repo

    async def execute(
        self,
        updated_by: UUID | None = None,
        **fields,
    ) -> dict[str, Any]:
        existing = await self.settings_repo.get()
        current = existing.security_settings or {}
        merged = {**current, **fields}
        cfg = await self.settings_repo.upsert(
            security_settings=merged,
            updated_by=updated_by,
        )
        return {
            **(cfg.security_settings or {}),
            "updated_at": cfg.updated_at.isoformat() if cfg.updated_at else None,
            "updated_by": str(cfg.updated_by) if cfg.updated_by else None,
        }
