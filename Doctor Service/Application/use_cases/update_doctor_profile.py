import logging

from Application.dtos import DoctorDTO
from Domain.exceptions.domain_exceptions import DoctorNotFoundException
from Domain.interfaces.doctor_repository import IDoctorRepository
from Domain.interfaces.event_publisher import IEventPublisher

logger = logging.getLogger(__name__)


class UpdateDoctorProfileUseCase:
    def __init__(self, doctor_repo: IDoctorRepository, event_publisher: IEventPublisher | None = None):
        self.doctor_repo = doctor_repo
        self.event_publisher = event_publisher

    async def execute(self, dto: DoctorDTO) -> DoctorDTO:
        doctor = await self.doctor_repo.get_by_id(dto.user_id)
        if not doctor:
            raise DoctorNotFoundException(dto.user_id)

        doctor.full_name = dto.full_name
        doctor.title = dto.title
        doctor.experience_years = dto.experience_years
        doctor.specialty_id = dto.specialty_id

        saved = await self.doctor_repo.save(doctor)

        if saved.specialty_id and saved.experience_years is not None and self.event_publisher:
            try:
                await self.event_publisher.publish(
                    exchange_name="user_events", routing_key="profile.completed", message={"user_id": str(dto.user_id)}
                )
                logger.info(f"Event published: PROFILE_COMPLETED for doctor {dto.user_id}")
            except Exception as e:
                logger.error(f"Failed to publish PROFILE_COMPLETED event: {str(e)}")

        return DoctorDTO.model_validate(saved)
