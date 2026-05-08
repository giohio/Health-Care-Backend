from uuid import UUID

from infrastructure.database.models import User as UserModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class UpdateUserProfileUseCase:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def execute(
        self,
        *,
        user_id: UUID,
        caller_id: UUID,
        full_name: str | None = None,
        email: str | None = None,
        role: str | None = None,
        is_active: bool | None = None,
    ) -> dict:
        result = await self.session.execute(select(UserModel).where(UserModel.id == user_id))
        user = result.scalar_one_or_none()
        if user is None:
            raise LookupError("User not found")

        if all(v is None for v in (full_name, email, role, is_active)):
            raise ValueError("No fields provided for update")

        if email is not None:
            normalized_email = email.strip().lower()
            dup_result = await self.session.execute(
                select(UserModel).where(UserModel.email == normalized_email, UserModel.id != user_id)
            )
            if dup_result.scalar_one_or_none() is not None:
                raise ValueError("Email already exists")
            user.email = normalized_email

        if full_name is not None:
            cleaned_name = full_name.strip()
            if cleaned_name == "":
                raise ValueError("full_name cannot be empty")
            user.full_name = cleaned_name

        if role is not None:
            if caller_id == user_id:
                raise ValueError("Admin cannot change their own role")
            user.role = role

        if is_active is not None:
            if caller_id == user_id:
                raise ValueError("Admin cannot change their own active status")
            user.is_active = is_active

        await self.session.flush()

        return {
            "id": str(user.id),
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role,
            "is_active": user.is_active,
            "is_email_verified": user.is_email_verified,
            "is_profile_completed": user.is_profile_completed,
            "created_at": user.created_at.isoformat() if user.created_at else None,
        }
