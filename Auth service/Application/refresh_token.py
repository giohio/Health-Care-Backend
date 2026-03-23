from typing import Tuple

from Domain import IRefreshTokenRepository, IUserRepository, RefreshToken
from infrastructure.security.jwt_handler import JWTHandler


class RefreshTokenUseCase:
    def __init__(self, user_repo: IUserRepository, token_repo: IRefreshTokenRepository, jwt_handler: JWTHandler):
        self.user_repo = user_repo
        self.token_repo = token_repo
        self.jwt_handler = jwt_handler

    async def execute(self, refresh_token_value: str) -> Tuple[str, str, any]:
        token = await self.token_repo.get_by_token(refresh_token_value)
        if not token or not token.is_valid():
            raise ValueError("Invalid or expired refresh token")

        user = await self.user_repo.get_by_id(token.user_id)
        if not user or not user.can_login():
            raise ValueError("User not found or inactive")

        # Generate new tokens (Rotation)
        new_access_token = self.jwt_handler.create_access_token(
            user_id=user.id, role=user.role, is_profile_completed=user.is_profile_completed, expires_in=15
        )

        new_refresh_token = RefreshToken.generate_token(user_id=user.id, expires_in=30)

        # Revoke old token and save new one
        token.revoke(replaced_by_token_id=new_refresh_token.id)
        await self.token_repo.update(
            token.id,
            is_revoked=token.is_revoked,
            revoked_at=token.revoked_at,
            replaced_by_token_id=token.replaced_by_token_id,
        )
        await self.token_repo.create(new_refresh_token)

        return new_access_token, new_refresh_token.token_value, user
