from Domain import (
    PatientHealthBackground,
    IPatientHealthRepository,
    IPatientProfileRepository
)
from uuid_extension import UUID7
from Application.use_cases.profile_helpers import get_or_create_profile


class UpdateHealthBackgroundUseCase:
    def __init__(
        self,
        profile_repo: IPatientProfileRepository,
        health_repo: IPatientHealthRepository
    ):
        self.profile_repo = profile_repo
        self.health_repo = health_repo

    async def execute(self, user_id: UUID7, **fields) -> PatientHealthBackground:
        profile = await get_or_create_profile(self.profile_repo, user_id)

        health_bg = await self.health_repo.get_by_patient_id(profile.id)
        if not health_bg:
            health_bg = await self.health_repo.create(PatientHealthBackground(patient_id=profile.id))

        health_bg.update_background(**fields)

        updated_bg = await self.health_repo.update(
            profile.id,
            **{k: v for k, v in fields.items() if hasattr(health_bg, k)}
        )

        return updated_bg
