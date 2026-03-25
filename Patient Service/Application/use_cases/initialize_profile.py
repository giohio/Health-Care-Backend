from Domain import IPatientHealthRepository, IPatientProfileRepository, PatientHealthBackground, PatientProfile
from uuid_extension import UUID7


class InitializeProfileUseCase:
    def __init__(self, profile_repo: IPatientProfileRepository, health_repo: IPatientHealthRepository):
        self.profile_repo = profile_repo
        self.health_repo = health_repo

    async def execute(self, user_id: UUID7) -> PatientProfile:
        # Check if profile already exists to avoid duplicates
        existing_profile = await self.profile_repo.get_by_user_id(user_id)
        if existing_profile:
            return existing_profile

        # 1. Create blank profile
        profile = PatientProfile(user_id=user_id)
        created_profile = await self.profile_repo.create(profile)

        # 2. Create blank health background
        health_bg = PatientHealthBackground(patient_id=created_profile.id)
        await self.health_repo.create(health_bg)

        return created_profile
