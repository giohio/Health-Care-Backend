from Domain import IRefreshTokenRepository
from uuid_extension import UUID7


class LogOutUseCase:
    def __init__(self, token_repository: IRefreshTokenRepository):
        self.token_repository = token_repository

    async def execute(
        self, refresh_token_value: str | None, user_id: UUID7 | str | None, logout_all_devices: bool = False
    ):
        if logout_all_devices:
            if not user_id:
                raise ValueError("user_id required for logout_all_devices")
            await self.token_repository.revoke_all_for_user(user_id)
        else:
            if not refresh_token_value:
                raise ValueError("refresh_token required")
            token = await self.token_repository.get_by_token(refresh_token_value)
            if token and token.is_valid():
                token.revoke()
                await self.token_repository.update(
                    token.id, is_revoked=token.is_revoked, revoked_at=token.revoked_at, last_used_at=token.last_used_at
                )
