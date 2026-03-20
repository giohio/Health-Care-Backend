import json
import logging
from infrastructure import UserRepository

logger = logging.getLogger(__name__)

class ProfileCompletedHandler:
    def __init__(self, user_repository: UserRepository):
        self.user_repository = user_repository

    async def handle(self, data: dict):
        try:
            user_id = data.get("user_id")
            
            if not user_id:
                logger.error("Invalid PROFILE_COMPLETED event: user_id missing")
                return

            logger.info(f"Processing PROFILE_COMPLETED for user: {user_id}")
            
            # Update the user's profile completion status in Auth DB
            await self.user_repository.update(user_id=user_id, is_profile_completed=True)
            await self.user_repository.session.commit()
            logger.info(f"Updated is_profile_completed status for user: {user_id}")
            
        except Exception as e:
            logger.error(f"Error handling PROFILE_COMPLETED event: {str(e)}")
            raise
