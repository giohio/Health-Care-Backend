from Application.verify_email import generate_otp
from Domain.interfaces import IEventPublisher, IUserRepository
from infrastructure.repositories.otp_repository import OTPRepository


class RequestPasswordResetUseCase:
    def __init__(
        self,
        user_repository: IUserRepository,
        otp_repository: OTPRepository,
        event_publisher: IEventPublisher,
    ):
        self.user_repository = user_repository
        self.otp_repository = otp_repository
        self.event_publisher = event_publisher

    async def execute(self, email: str) -> None:
        user = await self.user_repository.get_by_email(email)
        # Keep generic behavior to avoid leaking account existence.
        if not user:
            return

        if await self.otp_repository.is_in_cooldown(str(user.id), purpose="password_reset_otp"):
            raise ValueError("Please wait before requesting a new reset code")

        otp = generate_otp()
        await self.otp_repository.save(str(user.id), otp, purpose="password_reset_otp")

        try:
            await self.event_publisher.publish(
                exchange="user_events",
                routing_key="user.password_reset_otp",
                message={"user_id": str(user.id), "email": user.email, "otp": otp},
            )
        except Exception:
            pass
