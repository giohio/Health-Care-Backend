from datetime import datetime
from typing import List
from sqlalchemy import select, delete, update
from uuid_extension import UUID7

from Domain import RefreshToken, IRefreshTokenRepository
from infrastructure.database import RefreshToken as RefreshTokenModel, AsyncSessionLocal


class RefreshTokenRepository(IRefreshTokenRepository):
    def __init__(self, session: AsyncSessionLocal):
        self.session = session

    async def create(self, refresh_token: RefreshToken) -> RefreshToken:
        model = RefreshTokenModel(
            id=refresh_token.id,
            user_id=refresh_token.user_id,
            token_value=refresh_token.token_value,
            expires_at=refresh_token.expires_at,
            is_revoked=refresh_token.is_revoked,
            revoked_at=refresh_token.revoked_at,
            replaced_by_token_id=refresh_token.replaced_by_token_id,
            created_at=refresh_token.created_at,
            last_used_at=refresh_token.last_used_at
        )
        self.session.add(model)
        await self.session.flush()
        return self._to_entity(model)

    async def get_by_token(self, token: str) -> RefreshToken | None:
        result = await self.session.execute(
            select(RefreshTokenModel).where(RefreshTokenModel.token_value == token)
        )
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def get_by_user_id(self, user_id: UUID7) -> List[RefreshToken]:
        result = await self.session.execute(
            select(RefreshTokenModel).where(RefreshTokenModel.user_id == user_id)
        )
        models = result.scalars().all()
        return [self._to_entity(model) for model in models]

    async def update(self, token_id: UUID7, **fields) -> RefreshToken:
        result = await self.session.execute(
            update(RefreshTokenModel)
            .where(RefreshTokenModel.id == token_id)
            .values(**fields)
            .returning(RefreshTokenModel)
        )
        model = result.scalar_one()
        return self._to_entity(model)

    async def delete(self, token: str) -> bool:
        result = await self.session.execute(
            delete(RefreshTokenModel).where(RefreshTokenModel.token_value == token)
        )
        return result.rowcount > 0

    async def delete_by_user_id(self, user_id: UUID7) -> bool:
        result = await self.session.execute(
            delete(RefreshTokenModel).where(RefreshTokenModel.user_id == user_id)
        )
        return result.rowcount > 0

    async def revoke_all_for_user(self, user_id: UUID7) -> bool:
        result = await self.session.execute(
            select(RefreshTokenModel).where(
                RefreshTokenModel.user_id == user_id,
                RefreshTokenModel.is_revoked.is_(False)
            )
        )
        models = result.scalars().all()
        for model in models:
            model.is_revoked = True
            model.revoked_at = datetime.now()

        return True

    def _to_entity(self, model: RefreshTokenModel) -> RefreshToken:
        return RefreshToken(
            id=model.id,
            user_id=model.user_id,
            token_value=model.token_value,
            expires_at=model.expires_at,
            is_revoked=model.is_revoked,
            revoked_at=model.revoked_at,
            replaced_by_token_id=model.replaced_by_token_id,
            created_at=model.created_at,
            last_used_at=model.last_used_at
        )
