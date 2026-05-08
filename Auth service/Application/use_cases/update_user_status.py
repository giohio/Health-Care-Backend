from uuid import UUID

from infrastructure.database.models import User as UserModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class UpdateUserStatusUseCase:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def execute(self, user_id: UUID, is_active: bool, caller_id: UUID) -> dict:
        if user_id == caller_id:
            raise ValueError("Admin cannot change their own active status")

        result = await self.session.execute(select(UserModel).where(UserModel.id == user_id))
        user = result.scalar_one_or_none()
        if user is None:
            raise LookupError("User not found")

        user.is_active = is_active
        await self.session.flush()

        return {
            "id": str(user.id),
            "email": user.email,
            "role": user.role,
            "is_active": user.is_active,
            "is_email_verified": user.is_email_verified,
            "is_profile_completed": user.is_profile_completed,
            "created_at": user.created_at.isoformat() if user.created_at else None,
        }
