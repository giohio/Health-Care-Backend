from typing import Any

from infrastructure.repositories.system_settings_repository import SystemSettingsRepository


class GetSecuritySettingsUseCase:
    def __init__(self, settings_repo: SystemSettingsRepository):
        self.settings_repo = settings_repo

    async def execute(self) -> dict[str, Any]:
        cfg = await self.settings_repo.get()
        defaults = {
            "two_factor": False,
            "session_timeout_minutes": 30,
            "login_attempt_limit": 5,
            "audit_log": True,
            "password_rules": [],
        }
        current = cfg.security_settings or {}
        current = cfg.security_settings or {}
        merged = {**defaults, **current}
        return {
            **merged,
            "updated_at": cfg.updated_at.isoformat() if cfg.updated_at else None,
            "updated_by": str(cfg.updated_by) if cfg.updated_by else None,
        }
