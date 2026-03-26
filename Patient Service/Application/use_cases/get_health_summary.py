from Application.use_cases.profile_helpers import get_or_create_profile
from Domain import IPatientHealthRepository, IPatientProfileRepository
from uuid_extension import UUID7


class GetHealthSummaryUseCase:
    def __init__(self, profile_repo: IPatientProfileRepository, health_repo: IPatientHealthRepository):
        self.profile_repo = profile_repo
        self.health_repo = health_repo

    async def execute(self, user_id: UUID7):
        profile = await get_or_create_profile(self.profile_repo, user_id)
        health_bg = await self.health_repo.get_by_patient_id(profile.id)

        return {
            "user_id": str(user_id),
            "blood_type": health_bg.blood_type if health_bg else None,
            "allergies": health_bg.allergies if health_bg else [],
            "medical_conditions": getattr(health_bg, "medical_conditions", None) or [],
            "current_medications": getattr(health_bg, "current_medications", None) or [],
        }
