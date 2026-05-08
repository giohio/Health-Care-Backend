from Domain import IFileStorage, IPatientProfileRepository, PatientProfile
from infrastructure.config import settings
from uuid_extension import UUID7


class UploadProfilePhotoUseCase:
    ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}

    def __init__(self, profile_repo: IPatientProfileRepository, file_storage: IFileStorage):
        self.profile_repo = profile_repo
        self.file_storage = file_storage

    async def execute(self, user_id: UUID7, filename: str, content_type: str | None, data: bytes) -> str:
        if not filename:
            raise ValueError("Photo filename is required")
        if not data:
            raise ValueError("Photo file is empty")
        if len(data) > settings.MAX_UPLOAD_BYTES:
            raise ValueError("Photo file exceeds maximum allowed size")
        if content_type not in self.ALLOWED_CONTENT_TYPES:
            raise ValueError("Unsupported photo content type")

        profile = await self.profile_repo.get_by_user_id(user_id)
        if not profile:
            profile = await self.profile_repo.create(PatientProfile(user_id=user_id))

        photo_url, _ = self.file_storage.save(data, filename, subfolder="profile-photos")
        updated_profile = await self.profile_repo.update(
            profile.id,
            profile_photo_url=photo_url,
            avatar_url=photo_url,
            updated_at=profile.updated_at,
        )
        return updated_profile.profile_photo_url or updated_profile.avatar_url or photo_url