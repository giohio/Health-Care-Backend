from datetime import time
from uuid import UUID

from infrastructure.database.models import SystemConfig as SystemConfigModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


_DEFAULTS = dict(
    id=1,
    clinic_name="HealthAI Clinic",
    maintenance_mode=False,
    default_slot_duration_minutes=30,
    max_appointments_per_day=50,
    support_email=None,
    working_hours_start=time(7, 0),
    working_hours_end=time(18, 0),
    updated_by=None,
)


class SystemConfigRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self) -> SystemConfigModel:
        result = await self.session.execute(select(SystemConfigModel).where(SystemConfigModel.id == 1))
        model = result.scalar_one_or_none()
        if model is None:
            # Return a transient default object (not persisted yet)
            model = SystemConfigModel(**_DEFAULTS)
        return model

    async def upsert(self, updated_by: UUID | None = None, **fields) -> SystemConfigModel:
        result = await self.session.execute(select(SystemConfigModel).where(SystemConfigModel.id == 1))
        model = result.scalar_one_or_none()
        if model is None:
            init = {**_DEFAULTS, **fields}
            if updated_by is not None:
                init["updated_by"] = updated_by
            model = SystemConfigModel(**init)
            self.session.add(model)
        else:
            for k, v in fields.items():
                setattr(model, k, v)
            if updated_by is not None:
                model.updated_by = updated_by
        await self.session.flush()
        return model
