from datetime import datetime
from uuid import UUID

from infrastructure.database.models import SystemSettings as SystemSettingsModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class SystemSettingsRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self) -> SystemSettingsModel:
        result = await self.session.execute(
            select(SystemSettingsModel).where(SystemSettingsModel.id == 1)
        )
        model = result.scalar_one_or_none()
        if model is None:
            model = SystemSettingsModel(
                id=1,
                notification_settings=None,
                security_settings=None,
            )
            self.session.add(model)
            await self.session.flush()
        return model

    async def upsert(
        self,
        updated_by: UUID | None = None,
        notification_settings: dict | None = None,
        security_settings: dict | None = None,
    ) -> SystemSettingsModel:
        result = await self.session.execute(
            select(SystemSettingsModel).where(SystemSettingsModel.id == 1)
        )
        model = result.scalar_one_or_none()
        if model is None:
            init = {
                "id": 1,
                "notification_settings": notification_settings,
                "security_settings": security_settings,
            }
            if updated_by is not None:
                init["updated_by"] = updated_by
            model = SystemSettingsModel(**init)
            self.session.add(model)
        else:
            if notification_settings is not None:
                model.notification_settings = notification_settings
            if security_settings is not None:
                model.security_settings = security_settings
            if updated_by is not None:
                model.updated_by = updated_by
        await self.session.flush()
        return model
