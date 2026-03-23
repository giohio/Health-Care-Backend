import logging

from Domain.entities.doctor import Doctor
from Domain.interfaces.doctor_repository import IDoctorRepository
from uuid_extension import UUID7

logger = logging.getLogger(__name__)


class RegisterDoctorUseCase:
    def __init__(self, doctor_repo: IDoctorRepository):
        self.doctor_repo = doctor_repo

    async def execute(self, user_id: UUID7, full_name: str):
        existing = await self.doctor_repo.get_by_id(user_id)
        if existing:
            logger.warning(f"Doctor with user_id {user_id} already exists.")
            return

        doctor = Doctor(user_id=user_id, full_name=full_name, specialty_id=None)  # To be updated by the doctor later

        await self.doctor_repo.save(doctor)
        logger.info(f"Registered new doctor: {full_name} ({user_id})")
