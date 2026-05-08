from uuid import UUID

from Application.use_cases.profile_helpers import get_or_create_profile
from Domain import IPatientHealthRepository, IPatientProfileRepository, PatientHealthBackground, PatientProfile
from typing import Tuple


class GetPatientSummaryUseCase:
    """
    Use case for fetching a patient's profile + health summary.

    Used by doctors/admins to view a patient's details.
    Patients cannot use this use case directly (route-level auth enforces that).
    """

    def __init__(
        self,
        profile_repo: IPatientProfileRepository,
        health_repo: IPatientHealthRepository,
    ) -> None:
        self.profile_repo = profile_repo
        self.health_repo = health_repo

    async def execute(self, patient_user_id: UUID) -> Tuple[PatientProfile, PatientHealthBackground]:
        """
        Fetch the profile and health background for a given patient user_id.

        Raises ValueError if the patient profile is not found.
        """
        profile = await self.profile_repo.get_by_user_id(patient_user_id)
        if not profile:
            raise ValueError(f"Patient profile not found for user_id={patient_user_id}")

        health_bg = await self.health_repo.get_by_patient_id(profile.id)
        if not health_bg:
            health_bg = PatientHealthBackground(patient_id=profile.id)

        return profile, health_bg
