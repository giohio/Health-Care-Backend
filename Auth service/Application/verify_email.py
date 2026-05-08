import secrets

from Domain.interfaces import IUserRepository
from infrastructure.repositories.otp_repository import OTPRepository


def generate_otp() -> str:
    """Generate a cryptographically secure 6-digit OTP."""
    return f"{secrets.randbelow(1_000_000):06d}"


class VerifyEmailUseCase:
    def __init__(self, user_repository: IUserRepository, otp_repository: OTPRepository):
        self.user_repository = user_repository
        self.otp_repository = otp_repository

    async def execute(self, email: str, otp: str) -> None:
        user = await self.user_repository.get_by_email(email)
        if not user:
            raise ValueError("Invalid email or OTP")

        if user.is_email_verified:
            raise ValueError("Email is already verified")

        stored_otp = await self.otp_repository.get(str(user.id))
        if stored_otp is None or stored_otp != otp:
            raise ValueError("Invalid email or OTP")

        await self.user_repository.update(user.id, is_email_verified=True)
        await self.otp_repository.delete(str(user.id))
