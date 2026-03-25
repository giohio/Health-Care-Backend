from typing import Tuple

from Application.use_cases.profile_helpers import get_or_create_profile
from Domain import IPatientHealthRepository, IPatientProfileRepository, PatientHealthBackground, PatientProfile
from uuid_extension import UUID7


class GetProfileUseCase:
    def __init__(self, profile_repo: IPatientProfileRepository, health_repo: IPatientHealthRepository):
        self.profile_repo = profile_repo
        self.health_repo = health_repo

    async def execute(self, user_id: UUID7) -> Tuple[PatientProfile, PatientHealthBackground]:
        profile = await get_or_create_profile(self.profile_repo, user_id)

        health_bg = await self.health_repo.get_by_patient_id(profile.id)
        if not health_bg:
            # Should not happen if initialized correctly, but as a fallback
            health_bg = PatientHealthBackground(patient_id=profile.id)

        return profile, health_bg
