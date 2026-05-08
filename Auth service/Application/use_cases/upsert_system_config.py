from datetime import time
from uuid import UUID

from infrastructure.repositories.system_config_repository import SystemConfigRepository


_VALID_SLOT_DURATIONS = {15, 30, 45, 60}


class UpsertSystemConfigUseCase:
    def __init__(self, config_repo: SystemConfigRepository):
        self.config_repo = config_repo

    async def execute(self, updated_by: UUID | None = None, **fields) -> dict:
        # Validate before writing
        if "default_slot_duration_minutes" in fields:
            val = fields["default_slot_duration_minutes"]
            if val not in _VALID_SLOT_DURATIONS:
                raise ValueError(f"default_slot_duration_minutes must be one of {sorted(_VALID_SLOT_DURATIONS)}")

        if "max_appointments_per_day" in fields:
            val = fields["max_appointments_per_day"]
            if not (1 <= val <= 200):
                raise ValueError("max_appointments_per_day must be between 1 and 200")

        if "working_hours_start" in fields and "working_hours_end" in fields:
            if fields["working_hours_start"] >= fields["working_hours_end"]:
                raise ValueError("working_hours_start must be before working_hours_end")
        elif "working_hours_start" in fields or "working_hours_end" in fields:
            # Partial update — fetch current to compare
            current = await self.config_repo.get()
            start = fields.get("working_hours_start", current.working_hours_start)
            end = fields.get("working_hours_end", current.working_hours_end)
            if start >= end:
                raise ValueError("working_hours_start must be before working_hours_end")

        cfg = await self.config_repo.upsert(updated_by=updated_by, **fields)
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
