import logging
from Application.use_cases.initialize_profile import InitializeProfileUseCase
from uuid_extension import UUID7
import json

logger = logging.getLogger(__name__)


class UserRegisteredHandler:
    def __init__(self, initialize_use_case: InitializeProfileUseCase):
        self.initialize_use_case = initialize_use_case

    async def handle(self, data: dict):
        """
        Processes USER_REGISTERED event.
        Raises exceptions to let the consumer handle Retries/Rejections.
        """

        user_id_str = data.get("user_id")
        if not user_id_str:
            logger.error("Missing user_id in event body")
            # Raise to trigger REJECT (no requeue)
            raise ValueError("Missing user_id")

        try:
            user_id = UUID7(user_id_str)
            logger.info(f"Initializing profile for user {user_id}")

            await self.initialize_use_case.execute(user_id)

            logger.info(f"Successfully initialized profile for user {user_id}")
        except Exception as e:
            # Technical error (DB down, etc.) - Raise to trigger NACK (requeue)
            logger.error(f"Technical failure initializing profile for {user_id_str}: {str(e)}")
            raise


proxy_handler = UserRegisteredHandler
