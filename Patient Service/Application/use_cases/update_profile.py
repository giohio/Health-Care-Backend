import logging
from Domain import (
    PatientProfile,
    IPatientProfileRepository,
    IEventPublisher
)
from uuid_extension import UUID7

logger = logging.getLogger(__name__)


class UpdateProfileUseCase:
    def __init__(
        self,
        profile_repo: IPatientProfileRepository,
        event_publisher: IEventPublisher | None = None
    ):
        self.profile_repo = profile_repo
        self.event_publisher = event_publisher

    async def execute(self, user_id: UUID7, **fields) -> PatientProfile:
        profile = await self.profile_repo.get_by_user_id(user_id)
        if not profile:
            # Auto-create a blank profile if not yet provisioned via event
            profile = await self.profile_repo.create(PatientProfile(user_id=user_id))

        # Update profile fields
        profile.update_profile(**fields)

        updated_profile = await self.profile_repo.update(
            profile.id,
            **{k: v for k, v in fields.items() if hasattr(profile, k)}
        )

        # Check for profile completion
        if self._is_completed(updated_profile):
            await self._notify_profile_completed(user_id)

        return updated_profile

    def _is_completed(self, profile: PatientProfile) -> bool:
        mandatory_fields = [
            profile.full_name,
            profile.date_of_birth,
            profile.gender
        ]
        return all(field is not None and field != "" for field in mandatory_fields)

    async def _notify_profile_completed(self, user_id: UUID7):
        """
        Notifies that the profile is completed using an event publisher.
        """
        if self.event_publisher:
            try:
                await self.event_publisher.publish(
                    exchange_name="user_events",
                    routing_key="profile.completed",
                    message={"user_id": str(user_id)}
                )
                logger.info(f"Event published: PROFILE_COMPLETED for user {user_id}")
            except Exception as e:
                # Event publishing failure should be logged but maybe not crash the user update
                logger.error(f"Failed to publish PROFILE_COMPLETED event: {str(e)}")
        else:
            logger.warning(f"No event publisher configured. Completion for user {user_id} not broadcast.")
