from Application.verify_email import generate_otp
from Domain.interfaces import IEventPublisher, IUserRepository
from infrastructure.repositories.otp_repository import OTPRepository


class ResendOTPUseCase:
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
        # Use a generic error to avoid leaking whether the email exists
        if not user:
            return

        if user.is_email_verified:
            return

        if await self.otp_repository.is_in_cooldown(str(user.id)):
            raise ValueError("Please wait before requesting a new OTP")

        otp = generate_otp()
        await self.otp_repository.save(str(user.id), otp)

        try:
            await self.event_publisher.publish(
                exchange="user_events",
                routing_key="user.resend_otp",
                message={"user_id": str(user.id), "email": user.email, "otp": otp},
            )
        except Exception:
            pass
