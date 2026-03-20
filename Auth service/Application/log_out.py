from uuid_extension import UUID7
from Domain import IRefreshTokenRepository


class LogOutUseCase:
    def __init__(self, token_repository: IRefreshTokenRepository):
        self.token_repository = token_repository

    async def execute(
        self,
        refresh_token_value: str,
        user_id: UUID7,
        logout_all_devices: bool = False
    ):
        if logout_all_devices:
            await self.token_repository.revoke_all_for_user(user_id)
        else:
            token = await self.token_repository.get_by_token(refresh_token_value)
            if not token:
                raise ValueError("Invalid refresh token")
            token.revoke()
            await self.token_repository.update(
                token.id,
                is_revoked=token.is_revoked,
                revoked_at=token.revoked_at,
                last_used_at=token.last_used_at
            )
