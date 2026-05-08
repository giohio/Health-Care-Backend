import logging
from typing import Annotated

from Application import LoginUseCase, LogOutUseCase, RefreshTokenUseCase, RegisterService, RequestPasswordResetUseCase, ResendOTPUseCase, ResetPasswordUseCase, VerifyEmailUseCase
from Domain.entities.user import UserRole
from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Response, status
from infrastructure import UserRepository, settings
from infrastructure.repositories.otp_repository import OTPRepository
from presentation.dependencies import (
    get_db,
    get_login_use_case,
    get_logout_use_case,
    get_otp_repository,
    get_request_password_reset_use_case,
    get_refresh_token_use_case,
    get_register_service,
    get_reset_password_use_case,
    get_resend_otp_use_case,
    get_user_repository,
    get_verify_email_use_case,
)
from presentation.schema import (
    LogoutRequest,
    MeResponse,
    ForgotPasswordRequest,
    RefreshTokenRequest,
    RegisterStaffRequest,
    ResendOTPRequest,
    ResetPasswordRequest,
    TokenResponse,
    UserLogin,
    UserRegister,
    UserResponse,
    VerifyEmailRequest,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(tags=["Authentication"])
logger = logging.getLogger(__name__)

INTERNAL_SERVER_ERROR_MSG = "Internal server error"
_USER_NOT_FOUND = "User not found"


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    user_data: UserRegister,
    register_service: Annotated[RegisterService, Depends(get_register_service)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    try:
        # Call service to handle logic with dict unpacking
        user = await register_service.execute(**user_data.model_dump())
        await db.commit()
        return user
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except IntegrityError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already exists")
    except Exception as e:
        # Catch unexpected system errors
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Internal server error: {str(e)}"
        )


@router.post("/admin/register-staff", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register_staff(
    user_data: RegisterStaffRequest,
    register_service: Annotated[RegisterService, Depends(get_register_service)],
    db: Annotated[AsyncSession, Depends(get_db)],
    x_user_role: str | None = Header(default=None, alias="X-User-Role", include_in_schema=False),
):
    if x_user_role != UserRole.ADMIN.value:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")

    if user_data.role not in (UserRole.DOCTOR, UserRole.ADMIN):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid role for staff")

    try:
        user = await register_service.execute(
            email=user_data.email,
            password=user_data.password,
            role=user_data.role,
            full_name=user_data.full_name,
        )
        await db.commit()
        return user
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/login", response_model=TokenResponse)
async def login(
    login_data: UserLogin,
    response: Response,
    login_use_case: Annotated[LoginUseCase, Depends(get_login_use_case)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    try:
        access_token, refresh_token, user = await login_use_case.execute(**login_data.model_dump())
        await db.commit()

        # Set HttpOnly cookies
        response.set_cookie(
            key="access_token",
            value=access_token,
            httponly=True,
            secure=False,  # Set to True in production with HTTPS
            samesite="lax",
            max_age=15 * 60,  # 15 minutes
            path="/",
        )
        response.set_cookie(
            key="refresh_token",
            value=refresh_token,
            httponly=True,
            secure=False,
            samesite="lax",
            max_age=7 * 24 * 60 * 60,  # 7 days
            path="/",
        )

        return {"access_token": access_token, "refresh_token": refresh_token, "user": user}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))
    except Exception:
        logger.exception("Unexpected error during login")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=INTERNAL_SERVER_ERROR_MSG)


@router.post("/logout")
async def logout(
    logout_data: LogoutRequest,
    response: Response,
    logout_use_case: Annotated[LogOutUseCase, Depends(get_logout_use_case)],
    db: Annotated[AsyncSession, Depends(get_db)],
    refresh_token: str | None = Cookie(default=None),
    x_user_id: str | None = Header(default=None, alias="X-User-Id", include_in_schema=False),
):
    try:
        token_to_use = logout_data.refresh_token or refresh_token

        await logout_use_case.execute(
            refresh_token_value=token_to_use, user_id=x_user_id, logout_all_devices=logout_data.logout_all_devices
        )
        await db.commit()

        return {"success": True, "message": "Successfully logged out"}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=INTERNAL_SERVER_ERROR_MSG)
    finally:
        # Best effort logout: always clear client cookies.
        response.delete_cookie("access_token", path="/")
        response.delete_cookie("refresh_token", path="/")


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    refresh_data: RefreshTokenRequest,
    response: Response,
    refresh_use_case: Annotated[RefreshTokenUseCase, Depends(get_refresh_token_use_case)],
    db: Annotated[AsyncSession, Depends(get_db)],
    refresh_token_cookie: str | None = Cookie(default=None, alias="refresh_token"),
):
    try:
        token_to_use = refresh_data.refresh_token or refresh_token_cookie
        if not token_to_use:
            raise ValueError("No refresh token provided")

        access_token, refresh_token, user = await refresh_use_case.execute(refresh_token_value=token_to_use)
        await db.commit()

        # Set new cookies
        response.set_cookie(
            key="access_token", value=access_token, httponly=True, secure=False, samesite="lax", max_age=15 * 60, path="/"
        )
        response.set_cookie(
            key="refresh_token",
            value=refresh_token,
            httponly=True,
            secure=False,
            samesite="lax",
            max_age=7 * 24 * 60 * 60,
            path="/",
        )

        return {"access_token": access_token, "refresh_token": refresh_token, "user": user}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))
    except Exception:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=INTERNAL_SERVER_ERROR_MSG)


@router.get("/me", response_model=MeResponse)
async def get_me(
    x_user_id: str | None = Header(default=None, alias="X-User-Id", include_in_schema=False),
    user_repo: UserRepository = Depends(get_user_repository),
):
    if not x_user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthenticated")
    try:
        from uuid import UUID

        user = await user_repo.get_by_id(UUID(x_user_id))
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_USER_NOT_FOUND)
        return MeResponse(
            id=user.id,
            email=user.email,
            role=user.role,
            is_active=user.is_active,
            created_at=user.created_at.isoformat(),
        )
    except HTTPException:
        raise
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid user ID")
    except Exception:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=INTERNAL_SERVER_ERROR_MSG)


@router.get("/internal/users/{user_id}")
async def get_user_internal(
    user_id: str,
    user_repo: UserRepository = Depends(get_user_repository),
):
    """Internal endpoint for service-to-service email lookup. Not exposed via Kong."""
    try:
        from uuid import UUID

        user = await user_repo.get_by_id(UUID(user_id))
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_USER_NOT_FOUND)
        return {"id": str(user.id), "email": user.email}
    except HTTPException:
        raise
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid user ID")
    except Exception:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=INTERNAL_SERVER_ERROR_MSG)


@router.post("/verify-email", status_code=status.HTTP_200_OK)
async def verify_email(
    data: VerifyEmailRequest,
    verify_use_case: Annotated[VerifyEmailUseCase, Depends(get_verify_email_use_case)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    try:
        await verify_use_case.execute(email=data.email, otp=data.otp)
        await db.commit()
        return {"message": "Email verified successfully"}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception:
        logger.exception("Unexpected error during email verification")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=INTERNAL_SERVER_ERROR_MSG)


@router.post("/resend-otp", status_code=status.HTTP_200_OK)
async def resend_otp(
    data: ResendOTPRequest,
    resend_use_case: Annotated[ResendOTPUseCase, Depends(get_resend_otp_use_case)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    try:
        await resend_use_case.execute(email=data.email)
        await db.commit()
        return {"message": "If the email is registered and unverified, a new OTP has been sent"}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(e))
    except Exception:
        logger.exception("Unexpected error during OTP resend")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=INTERNAL_SERVER_ERROR_MSG)


@router.post("/forgot-password", status_code=status.HTTP_200_OK)
async def forgot_password(
    data: ForgotPasswordRequest,
    use_case: Annotated[RequestPasswordResetUseCase, Depends(get_request_password_reset_use_case)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    try:
        await use_case.execute(email=data.email)
        await db.commit()
        return {"message": "If the email is registered, a reset code has been sent"}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(e))
    except Exception:
        logger.exception("Unexpected error during forgot-password")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=INTERNAL_SERVER_ERROR_MSG)


@router.post("/reset-password", status_code=status.HTTP_200_OK)
async def reset_password(
    data: ResetPasswordRequest,
    use_case: Annotated[ResetPasswordUseCase, Depends(get_reset_password_use_case)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    try:
        await use_case.execute(email=data.email, otp=data.otp, new_password=data.new_password)
        await db.commit()
        return {"message": "Password reset successful"}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception:
        logger.exception("Unexpected error during reset-password")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=INTERNAL_SERVER_ERROR_MSG)


@router.get("/dev/otp/{email}", include_in_schema=False)
async def dev_get_otp(
    email: str,
    user_repo: UserRepository = Depends(get_user_repository),
    otp_repo: OTPRepository = Depends(get_otp_repository),
):
    """DEBUG ONLY — returns stored OTP for an email. Only available when DEBUG=True."""
    if not settings.DEBUG:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    user = await user_repo.get_by_email(email)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_USER_NOT_FOUND)

    otp = await otp_repo.get(str(user.id))
    if not otp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No pending OTP")

    return {"otp": otp}
