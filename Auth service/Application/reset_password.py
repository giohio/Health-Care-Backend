from Domain.interfaces import IUserRepository
from infrastructure.repositories.otp_repository import OTPRepository


class ResetPasswordUseCase:
    def __init__(self, user_repository: IUserRepository, otp_repository: OTPRepository, password_hasher):
        self.user_repository = user_repository
        self.otp_repository = otp_repository
        self.password_hasher = password_hasher

    async def execute(self, email: str, otp: str, new_password: str) -> None:
        user = await self.user_repository.get_by_email(email)
        if not user:
            raise ValueError("Invalid email or OTP")

        stored_otp = await self.otp_repository.get(str(user.id), purpose="password_reset_otp")
        if stored_otp is None or stored_otp != otp:
            raise ValueError("Invalid email or OTP")

        hashed_password = await self.password_hasher.hash(new_password)
        await self.user_repository.update(user.id, hashed_password=hashed_password)
        await self.otp_repository.delete(str(user.id), purpose="password_reset_otp")
