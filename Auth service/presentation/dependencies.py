from infrastructure import (
    AsyncSessionLocal,
    UserRepository,
    RefreshTokenRepository,
    JWTHandler,
    PasswordHasher,
    settings
)
from shared_lib.messaging import BasePublisher
from Application import LoginUseCase, RegisterService, LogOutUseCase, RefreshTokenUseCase
from typing import AsyncGenerator
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from functools import lru_cache


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@lru_cache()
def get_password_hasher() -> PasswordHasher:
    return PasswordHasher()


@lru_cache()
def get_jwt_handler() -> JWTHandler:
    return JWTHandler()


@lru_cache()
def get_event_publisher() -> BasePublisher:
    return BasePublisher(settings.RABBITMQ_URL)


def get_user_repository(session: AsyncSession = Depends(get_db)) -> UserRepository:
    return UserRepository(session)


def get_refresh_token_repository(session: AsyncSession = Depends(get_db)) -> RefreshTokenRepository:
    return RefreshTokenRepository(session)


def get_register_service(
    user_repo: UserRepository = Depends(get_user_repository),
    password_hasher: PasswordHasher = Depends(get_password_hasher),
    event_publisher: BasePublisher = Depends(get_event_publisher)
) -> RegisterService:
    return RegisterService(user_repo, password_hasher, event_publisher)


def get_login_use_case(
    user_repo: UserRepository = Depends(get_user_repository),
    token_repo: RefreshTokenRepository = Depends(get_refresh_token_repository),
    password_hasher: PasswordHasher = Depends(get_password_hasher),
    jwt_handler: JWTHandler = Depends(get_jwt_handler)
) -> LoginUseCase:
    return LoginUseCase(user_repo, token_repo, password_hasher, jwt_handler)


def get_logout_use_case(
    token_repo: RefreshTokenRepository = Depends(get_refresh_token_repository)
) -> LogOutUseCase:
    return LogOutUseCase(token_repo)


def get_refresh_token_use_case(
    user_repo: UserRepository = Depends(get_user_repository),
    token_repo: RefreshTokenRepository = Depends(get_refresh_token_repository),
    jwt_handler: JWTHandler = Depends(get_jwt_handler)
) -> RefreshTokenUseCase:
    return RefreshTokenUseCase(user_repo, token_repo, jwt_handler)
