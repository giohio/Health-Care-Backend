import uuid
from datetime import datetime

from infrastructure.database.models import PatientProfileModel, PatientVitalsModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from uuid_extension import UUID7


class VitalsRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def _get_profile_id(self, user_id: UUID7):
        """Resolve patient_profiles.id from user_id."""
        result = await self.session.execute(
            select(PatientProfileModel).where(PatientProfileModel.user_id == uuid.UUID(str(user_id)))
        )
        profile = result.scalar_one_or_none()
        return profile.id if profile else None

    async def create(self, patient_id: UUID7, recorded_by: UUID7, vitals_data: dict):
        profile_id = await self._get_profile_id(patient_id)
        if not profile_id:
            raise ValueError(f"Patient profile not found for user {patient_id}")

        model = PatientVitalsModel(
            patient_id=uuid.UUID(str(profile_id)),
            recorded_by=uuid.UUID(str(recorded_by)),
            recorded_at=datetime.now(),
            **vitals_data,
        )
        self.session.add(model)
        await self.session.flush()
        return model

    async def get_latest(self, patient_id: UUID7):
        profile_id = await self._get_profile_id(patient_id)
        if not profile_id:
            return None
        result = await self.session.execute(
            select(PatientVitalsModel)
            .where(PatientVitalsModel.patient_id == uuid.UUID(str(profile_id)))
            .order_by(PatientVitalsModel.recorded_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_by_patient(self, patient_id: UUID7, limit: int, offset: int):
        profile_id = await self._get_profile_id(patient_id)
        if not profile_id:
            return []
        result = await self.session.execute(
            select(PatientVitalsModel)
            .where(PatientVitalsModel.patient_id == uuid.UUID(str(profile_id)))
            .order_by(PatientVitalsModel.recorded_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return result.scalars().all()
