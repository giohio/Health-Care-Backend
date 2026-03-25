from Domain import IPatientHealthRepository, IPatientProfileRepository, PatientHealthBackground, PatientProfile
from infrastructure.database.models import PatientHealthBackgroundModel, PatientProfileModel
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from uuid_extension import UUID7


class PatientProfileRepository(IPatientProfileRepository):
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, profile: PatientProfile) -> PatientProfile:
        model = PatientProfileModel(
            id=profile.id,
            user_id=profile.user_id,
            full_name=profile.full_name,
            date_of_birth=profile.date_of_birth,
            gender=profile.gender,
            phone_number=profile.phone_number,
            address=profile.address,
            avatar_url=profile.avatar_url,
            created_at=profile.created_at,
            updated_at=profile.updated_at,
        )
        self.session.add(model)
        await self.session.flush()
        return self._to_entity(model)

    async def get_by_id(self, profile_id: UUID7) -> PatientProfile | None:
        result = await self.session.execute(select(PatientProfileModel).where(PatientProfileModel.id == profile_id))
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def get_by_user_id(self, user_id: UUID7) -> PatientProfile | None:
        result = await self.session.execute(select(PatientProfileModel).where(PatientProfileModel.user_id == user_id))
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def update(self, profile_id: UUID7, **fields) -> PatientProfile:
        result = await self.session.execute(
            update(PatientProfileModel)
            .where(PatientProfileModel.id == profile_id)
            .values(**fields)
            .returning(PatientProfileModel)
        )
        model = result.scalar_one()
        return self._to_entity(model)

    async def delete(self, profile_id: UUID7) -> bool:
        result = await self.session.execute(delete(PatientProfileModel).where(PatientProfileModel.id == profile_id))
        return result.rowcount > 0

    def _to_entity(self, model: PatientProfileModel) -> PatientProfile:
        return PatientProfile(
            id=model.id,
            user_id=model.user_id,
            full_name=model.full_name,
            date_of_birth=model.date_of_birth,
            gender=model.gender,
            phone_number=model.phone_number,
            address=model.address,
            avatar_url=model.avatar_url,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )


class PatientHealthRepository(IPatientHealthRepository):
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, background: PatientHealthBackground) -> PatientHealthBackground:
        model = PatientHealthBackgroundModel(
            patient_id=background.patient_id,
            blood_type=background.blood_type,
            height_cm=background.height_cm,
            weight_kg=background.weight_kg,
            allergies=background.allergies,
            chronic_conditions=background.chronic_conditions,
        )
        self.session.add(model)
        await self.session.flush()
        return self._to_entity(model)

    async def get_by_patient_id(self, patient_id: UUID7) -> PatientHealthBackground | None:
        result = await self.session.execute(
            select(PatientHealthBackgroundModel).where(PatientHealthBackgroundModel.patient_id == patient_id)
        )
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def update(self, patient_id: UUID7, **fields) -> PatientHealthBackground:
        result = await self.session.execute(
            update(PatientHealthBackgroundModel)
            .where(PatientHealthBackgroundModel.patient_id == patient_id)
            .values(**fields)
            .returning(PatientHealthBackgroundModel)
        )
        model = result.scalar_one()
        return self._to_entity(model)

    def _to_entity(self, model: PatientHealthBackgroundModel) -> PatientHealthBackground:
        return PatientHealthBackground(
            patient_id=model.patient_id,
            blood_type=model.blood_type,
            height_cm=model.height_cm,
            weight_kg=model.weight_kg,
            allergies=model.allergies,
            chronic_conditions=model.chronic_conditions,
        )
