from typing import Annotated
import logging

from Application import LoginUseCase, LogOutUseCase, RefreshTokenUseCase, RegisterService
from Domain.entities.user import UserRole
from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Response, status
from sqlalchemy.exc import IntegrityError
from presentation.dependencies import (
    get_login_use_case,
    get_logout_use_case,
    get_refresh_token_use_case,
    get_register_service,
    get_db,
)
from sqlalchemy.ext.asyncio import AsyncSession
from presentation.schema import (
    LogoutRequest,
    RefreshTokenRequest,
    RegisterStaffRequest,
    TokenResponse,
    UserLogin,
    UserRegister,
    UserResponse,
)

router = APIRouter(tags=["Authentication"])
logger = logging.getLogger(__name__)

INTERNAL_SERVER_ERROR_MSG = "Internal server error"


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    user_data: UserRegister, register_service: Annotated[RegisterService, Depends(get_register_service)],
    db: AsyncSession = Depends(get_db),
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
    x_user_role: str | None = Header(default=None, alias="X-User-Role"),
    db: AsyncSession = Depends(get_db),
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
        )
        await db.commit()
        return user
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=INTERNAL_SERVER_ERROR_MSG)


@router.post("/login", response_model=TokenResponse)
async def login(
    login_data: UserLogin,
    response: Response,
    login_use_case: Annotated[LoginUseCase, Depends(get_login_use_case)],
    db: AsyncSession = Depends(get_db),
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
        )
        response.set_cookie(
            key="refresh_token",
            value=refresh_token,
            httponly=True,
            secure=False,
            samesite="lax",
            max_age=7 * 24 * 60 * 60,  # 7 days
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
    refresh_token: str | None = Cookie(default=None),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
    db: AsyncSession = Depends(get_db),
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
        response.delete_cookie("access_token")
        response.delete_cookie("refresh_token")


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    refresh_data: RefreshTokenRequest,
    response: Response,
    refresh_use_case: Annotated[RefreshTokenUseCase, Depends(get_refresh_token_use_case)],
    refresh_token_cookie: str | None = Cookie(default=None, alias="refresh_token"),
    db: AsyncSession = Depends(get_db),
):
    try:
        token_to_use = refresh_data.refresh_token or refresh_token_cookie
        if not token_to_use:
            raise ValueError("No refresh token provided")

        access_token, refresh_token, user = await refresh_use_case.execute(refresh_token_value=token_to_use)
        await db.commit()

        # Set new cookies
        response.set_cookie(
            key="access_token", value=access_token, httponly=True, secure=False, samesite="lax", max_age=15 * 60
        )
        response.set_cookie(
            key="refresh_token",
            value=refresh_token,
            httponly=True,
            secure=False,
            samesite="lax",
            max_age=7 * 24 * 60 * 60,
        )

        return {"access_token": access_token, "refresh_token": refresh_token, "user": user}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))
    except Exception:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=INTERNAL_SERVER_ERROR_MSG)
