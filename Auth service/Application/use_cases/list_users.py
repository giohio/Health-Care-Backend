import math
from typing import List
from uuid import UUID

from Domain.entities.user import UserRole
from infrastructure.database.models import User as UserModel
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession


class ListUsersUseCase:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def execute(
        self,
        role: str | None = None,
        search: str | None = None,
        is_active: bool | None = None,
        page: int = 1,
        limit: int = 20,
    ) -> dict:
        limit = min(limit, 100)
        offset = (page - 1) * limit

        conditions = []
        if role:
            conditions.append(UserModel.role == role)
        if search:
            conditions.append(UserModel.email.ilike(f"%{search}%"))
        if is_active is not None:
            conditions.append(UserModel.is_active == is_active)

        where_clause = and_(*conditions) if conditions else True

        count_result = await self.session.execute(
            select(func.count()).select_from(UserModel).where(where_clause)
        )
        total = count_result.scalar() or 0

        result = await self.session.execute(
            select(UserModel)
            .where(where_clause)
            .order_by(UserModel.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        users = result.scalars().all()

        return {
            "users": [
                {
                    "id": str(u.id),
                    "email": u.email,
                    "full_name": getattr(u, "full_name", None),
                    "role": u.role,
                    "is_active": u.is_active,
                    "is_email_verified": u.is_email_verified,
                    "is_profile_completed": u.is_profile_completed,
                    "created_at": u.created_at.isoformat() if u.created_at else None,
                }
                for u in users
            ],
            "total": total,
            "page": page,
            "limit": limit,
            "total_pages": math.ceil(total / limit) if limit else 1,
        }
