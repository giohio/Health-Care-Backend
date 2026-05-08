from functools import lru_cache
from typing import AsyncGenerator

import redis.asyncio as aioredis
from Application import LoginUseCase, LogOutUseCase, RefreshTokenUseCase, RegisterService, ResendOTPUseCase, VerifyEmailUseCase
from Application import RequestPasswordResetUseCase, ResetPasswordUseCase
from Application.use_cases.get_system_config import GetSystemConfigUseCase
from Application.use_cases.list_users import ListUsersUseCase
from Application.use_cases.update_user_profile import UpdateUserProfileUseCase
from Application.use_cases.update_user_status import UpdateUserStatusUseCase
from Application.use_cases.upsert_system_config import UpsertSystemConfigUseCase
from Domain.interfaces import IEventPublisher
from fastapi import Depends
from infrastructure import AsyncSessionLocal, JWTHandler, OTPRepository, PasswordHasher, RefreshTokenRepository, UserRepository, settings
from infrastructure.publishers.outbox_event_publisher import OutboxEventPublisher
from infrastructure.repositories.system_config_repository import SystemConfigRepository
from sqlalchemy.ext.asyncio import AsyncSession


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
def get_redis_client() -> aioredis.Redis:
    return aioredis.from_url(settings.REDIS_URL, decode_responses=False)


def get_otp_repository() -> OTPRepository:
    return OTPRepository(get_redis_client())


def get_event_publisher(session: AsyncSession = Depends(get_db)) -> IEventPublisher:
    return OutboxEventPublisher(session)


def get_user_repository(session: AsyncSession = Depends(get_db)) -> UserRepository:
    return UserRepository(session)


def get_refresh_token_repository(session: AsyncSession = Depends(get_db)) -> RefreshTokenRepository:
    return RefreshTokenRepository(session)


def get_register_service(
    user_repo: UserRepository = Depends(get_user_repository),
    password_hasher: PasswordHasher = Depends(get_password_hasher),
    event_publisher: IEventPublisher = Depends(get_event_publisher),
    otp_repo: OTPRepository = Depends(get_otp_repository),
) -> RegisterService:
    return RegisterService(user_repo, password_hasher, event_publisher, otp_repo)


def get_login_use_case(
    user_repo: UserRepository = Depends(get_user_repository),
    token_repo: RefreshTokenRepository = Depends(get_refresh_token_repository),
    password_hasher: PasswordHasher = Depends(get_password_hasher),
    jwt_handler: JWTHandler = Depends(get_jwt_handler),
) -> LoginUseCase:
    return LoginUseCase(user_repo, token_repo, password_hasher, jwt_handler)


def get_logout_use_case(token_repo: RefreshTokenRepository = Depends(get_refresh_token_repository)) -> LogOutUseCase:
    return LogOutUseCase(token_repo)


def get_refresh_token_use_case(
    user_repo: UserRepository = Depends(get_user_repository),
    token_repo: RefreshTokenRepository = Depends(get_refresh_token_repository),
    jwt_handler: JWTHandler = Depends(get_jwt_handler),
) -> RefreshTokenUseCase:
    return RefreshTokenUseCase(user_repo, token_repo, jwt_handler)


def get_verify_email_use_case(
    user_repo: UserRepository = Depends(get_user_repository),
    otp_repo: OTPRepository = Depends(get_otp_repository),
) -> VerifyEmailUseCase:
    return VerifyEmailUseCase(user_repo, otp_repo)


def get_resend_otp_use_case(
    user_repo: UserRepository = Depends(get_user_repository),
    otp_repo: OTPRepository = Depends(get_otp_repository),
    event_publisher: IEventPublisher = Depends(get_event_publisher),
) -> ResendOTPUseCase:
    return ResendOTPUseCase(user_repo, otp_repo, event_publisher)


def get_request_password_reset_use_case(
    user_repo: UserRepository = Depends(get_user_repository),
    otp_repo: OTPRepository = Depends(get_otp_repository),
    event_publisher: IEventPublisher = Depends(get_event_publisher),
) -> RequestPasswordResetUseCase:
    return RequestPasswordResetUseCase(user_repo, otp_repo, event_publisher)


def get_reset_password_use_case(
    user_repo: UserRepository = Depends(get_user_repository),
    otp_repo: OTPRepository = Depends(get_otp_repository),
    password_hasher: PasswordHasher = Depends(get_password_hasher),
) -> ResetPasswordUseCase:
    return ResetPasswordUseCase(user_repo, otp_repo, password_hasher)


# ── Admin dependencies ────────────────────────────────────────────────────────

def get_system_config_repository(session: AsyncSession = Depends(get_db)) -> SystemConfigRepository:
    return SystemConfigRepository(session)


def get_get_system_config_use_case(
    config_repo: SystemConfigRepository = Depends(get_system_config_repository),
) -> GetSystemConfigUseCase:
    return GetSystemConfigUseCase(config_repo)


def get_upsert_system_config_use_case(
    config_repo: SystemConfigRepository = Depends(get_system_config_repository),
) -> UpsertSystemConfigUseCase:
    return UpsertSystemConfigUseCase(config_repo)


def get_list_users_use_case(session: AsyncSession = Depends(get_db)) -> ListUsersUseCase:
    return ListUsersUseCase(session)


def get_update_user_status_use_case(session: AsyncSession = Depends(get_db)) -> UpdateUserStatusUseCase:
    return UpdateUserStatusUseCase(session)


def get_update_user_profile_use_case(session: AsyncSession = Depends(get_db)) -> UpdateUserProfileUseCase:
    return UpdateUserProfileUseCase(session)


def get_system_settings_repository(session: AsyncSession = Depends(get_db)):
    from infrastructure.repositories.system_settings_repository import SystemSettingsRepository
    return SystemSettingsRepository(session)


def get_get_notification_settings_use_case(
    settings_repo=Depends(get_system_settings_repository),
):
    from Application.use_cases.get_notification_settings import GetNotificationSettingsUseCase
    return GetNotificationSettingsUseCase(settings_repo)


def get_upsert_notification_settings_use_case(
    settings_repo=Depends(get_system_settings_repository),
):
    from Application.use_cases.upsert_notification_settings import UpsertNotificationSettingsUseCase
    return UpsertNotificationSettingsUseCase(settings_repo)


def get_get_security_settings_use_case(
    settings_repo=Depends(get_system_settings_repository),
):
    from Application.use_cases.get_security_settings import GetSecuritySettingsUseCase
    return GetSecuritySettingsUseCase(settings_repo)


def get_upsert_security_settings_use_case(
    settings_repo=Depends(get_system_settings_repository),
):
    from Application.use_cases.upsert_security_settings import UpsertSecuritySettingsUseCase
    return UpsertSecuritySettingsUseCase(settings_repo)
