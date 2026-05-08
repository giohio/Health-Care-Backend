from infrastructure.repositories.system_config_repository import SystemConfigRepository


class GetSystemConfigUseCase:
    def __init__(self, config_repo: SystemConfigRepository):
        self.config_repo = config_repo

    async def execute(self) -> dict:
        cfg = await self.config_repo.get()
        return {
            "clinic_name": cfg.clinic_name,
            "maintenance_mode": cfg.maintenance_mode,
            "default_slot_duration_minutes": cfg.default_slot_duration_minutes,
            "max_appointments_per_day": cfg.max_appointments_per_day,
            "support_email": cfg.support_email,
            "working_hours_start": str(cfg.working_hours_start)[:5],
            "working_hours_end": str(cfg.working_hours_end)[:5],
            "updated_at": cfg.updated_at.isoformat() if cfg.updated_at else None,
            "updated_by": str(cfg.updated_by) if cfg.updated_by else None,
        }
