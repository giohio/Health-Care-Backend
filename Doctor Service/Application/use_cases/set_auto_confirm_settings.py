from Application.dtos import DoctorAutoConfirmSettingsResponse
from Domain.exceptions.domain_exceptions import DoctorNotFoundException
from Domain.interfaces.doctor_repository import IDoctorRepository
from uuid_extension import UUID7


class SetAutoConfirmSettingsUseCase:
    def __init__(self, doctor_repo: IDoctorRepository):
        self.doctor_repo = doctor_repo

    async def execute(
        self,
        doctor_id: UUID7,
        auto_confirm: bool,
        confirmation_timeout_minutes: int,
    ) -> DoctorAutoConfirmSettingsResponse:
        doctor = await self.doctor_repo.get_by_id(doctor_id)
        if not doctor:
            raise DoctorNotFoundException(doctor_id)

        if confirmation_timeout_minutes <= 0:
            raise ValueError("confirmation_timeout_minutes must be greater than 0")

        doctor.auto_confirm = auto_confirm
        doctor.confirmation_timeout_minutes = confirmation_timeout_minutes
        saved = await self.doctor_repo.save(doctor)

        return DoctorAutoConfirmSettingsResponse(
            user_id=saved.user_id,
            auto_confirm=saved.auto_confirm,
            confirmation_timeout_minutes=saved.confirmation_timeout_minutes,
        )
