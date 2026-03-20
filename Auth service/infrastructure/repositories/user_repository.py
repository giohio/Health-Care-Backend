from typing import List
from sqlalchemy import select, delete, update
from uuid_extension import UUID7

from Domain import User as UserEntity, IUserRepository
from infrastructure.database import User as UserModel, AsyncSessionLocal


class UserRepository(IUserRepository):
    def __init__(self, session: AsyncSessionLocal):
        self.session = session

    async def create(self, user: UserEntity) -> UserEntity:
        user_model = UserModel(
            id=user.id,
            email=user.email,
            hashed_password=user.hashed_password,
            role=user.role,
            is_active=user.is_active,
            is_deleted=user.is_deleted,
            is_email_verified=user.is_email_verified,
            is_profile_completed=user.is_profile_completed,
            created_at=user.created_at,
            updated_at=user.updated_at
        )
        self.session.add(user_model)
        await self.session.flush()
        return self._to_entity(user_model)

    async def get_by_id(self, user_id: UUID7) -> UserEntity | None:
        result = await self.session.execute(
            select(UserModel).where(UserModel.id == user_id)
        )
        user_model = result.scalar_one_or_none()
        return self._to_entity(user_model) if user_model else None

    async def get_by_username(self, username: str) -> UserEntity | None:
        # Kept for interface compatibility but uses email now
        return await self.get_by_email(username)

    async def get_by_email(self, email: str) -> UserEntity | None:
        result = await self.session.execute(
            select(UserModel).where(UserModel.email == email)
        )
        user_model = result.scalar_one_or_none()
        return self._to_entity(user_model) if user_model else None

    async def update(self, user_id: UUID7, **fields) -> UserEntity:
        result = await self.session.execute(
            update(UserModel)
            .where(UserModel.id == user_id)
            .values(**fields)
            .returning(UserModel)
        )
        user_model = result.scalar_one()
        return self._to_entity(user_model)

    async def delete(self, user_id: UUID7) -> bool:
        result = await self.session.execute(
            delete(UserModel).where(UserModel.id == user_id)
        )
        return result.rowcount > 0

    async def list(self) -> List[UserEntity]:
        result = await self.session.execute(select(UserModel))
        user_models = result.scalars().all()
        return [self._to_entity(model) for model in user_models]

    def _to_entity(self, user_model: UserModel) -> UserEntity:
        return UserEntity(
            id=user_model.id,
            email=user_model.email,
            hashed_password=user_model.hashed_password,
            role=user_model.role,
            is_active=user_model.is_active,
            is_deleted=user_model.is_deleted,
            is_email_verified=user_model.is_email_verified,
            is_profile_completed=user_model.is_profile_completed,
            created_at=user_model.created_at,
            updated_at=user_model.updated_at,
            deleted_at=user_model.deleted_at
        )
