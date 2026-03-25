from Domain import IPatientProfileRepository, PatientProfile
from uuid_extension import UUID7


async def get_or_create_profile(profile_repo: IPatientProfileRepository, user_id: UUID7) -> PatientProfile:
    """Return existing profile or create a blank one if missing."""
    profile = await profile_repo.get_by_user_id(user_id)
    if profile:
        return profile
    return await profile_repo.create(PatientProfile(user_id=user_id))
