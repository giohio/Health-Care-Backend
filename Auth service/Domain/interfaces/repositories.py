from abc import ABC, abstractmethod
from typing import List

from Domain.entities import RefreshToken, User
from uuid_extension import UUID7


class IUserRepository(ABC):
    @abstractmethod
    async def create(self, user: User) -> User:
        pass

    @abstractmethod
    async def get_by_id(self, user_id: UUID7) -> User | None:
        pass

    @abstractmethod
    async def get_by_email(self, email: str) -> User | None:
        pass

    @abstractmethod
    async def update(self, user_id: UUID7, **fields) -> User:
        pass

    @abstractmethod
    async def delete(self, user_id: UUID7) -> bool:
        pass

    @abstractmethod
    async def list(self) -> List[User]:
        pass


class IRefreshTokenRepository(ABC):
    @abstractmethod
    async def create(self, refresh_token: RefreshToken) -> RefreshToken:
        pass

    @abstractmethod
    async def get_by_token(self, token: str) -> RefreshToken | None:
        pass

    @abstractmethod
    async def get_by_user_id(self, user_id: UUID7) -> List[RefreshToken]:
        pass

    @abstractmethod
    async def update(self, token_id: UUID7, **fields) -> RefreshToken:
        pass

    @abstractmethod
    async def delete(self, token: str) -> bool:
        pass

    @abstractmethod
    async def delete_by_user_id(self, user_id: UUID7) -> bool:
        pass

    @abstractmethod
    async def revoke_all_for_user(self, user_id: UUID7) -> int:
        pass
