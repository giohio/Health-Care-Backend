from typing import Tuple

from Domain import IRefreshTokenRepository, IUserRepository, RefreshToken


class LoginUseCase:
    def __init__(self, user_repo: IUserRepository, token_repo: IRefreshTokenRepository, password_hasher, jwt_handler):
        self.user_repo = user_repo
        self.token_repo = token_repo
        self.password_hasher = password_hasher
        self.jwt_handler = jwt_handler

    async def execute(self, email: str, password: str) -> Tuple[str, str, any]:
        user = await self.user_repo.get_by_email(email)
        if not user:
            raise ValueError("User not found")

        if not self.password_hasher.verify(password, user.hashed_password):
            raise ValueError("Invalid password")

        if not user.can_login():
            raise ValueError("User is not active")

        access_token = self.jwt_handler.create_access_token(
            user_id=user.id,
            role=user.role,
            is_profile_completed=user.is_profile_completed,
            expires_in=15,
        )

        refresh_token = RefreshToken.generate_token(
            user_id=user.id,
            expires_in=30,
        )

        user.record_login()
        await self.user_repo.update(user.id, updated_at=user.updated_at)

        await self.token_repo.create(refresh_token)

        return access_token, refresh_token.token_value, user
