import logging
from uuid import UUID

from Application.use_cases.register_doctor import RegisterDoctorUseCase

logger = logging.getLogger(__name__)


class UserRegisteredHandler:
    def __init__(self, register_doctor_use_case: RegisterDoctorUseCase):
        self.register_doctor_use_case = register_doctor_use_case

    async def handle(self, data: dict):
        """
        Handles user.registered event.
        Only processes if role is 'doctor'.
        """
        role = data.get("role")
        if role != "doctor":
            logger.debug(f"Skipping registration for role: {role}")
            return

        user_id_str = data.get("user_id")
        full_name = data.get("full_name") or "New Doctor"

        if not user_id_str:
            logger.error("Missing user_id in event payload")
            return

        try:
            user_id = UUID(user_id_str)
            await self.register_doctor_use_case.execute(user_id, full_name)
            logger.info(f"Handled registration for doctor {full_name}")
        except Exception as e:
            logger.error(f"Failed to handle doctor registration: {str(e)}")
            raise  # Let consumer handle retry/reject
