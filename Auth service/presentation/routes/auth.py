from fastapi import APIRouter, Depends, HTTPException, status, Response, Cookie
from presentation.schema import (
    UserRegister, UserLogin, UserResponse, TokenResponse,
    RefreshTokenRequest, LogoutRequest
)
from typing import Annotated
from presentation.dependencies import (
    get_register_service, get_login_use_case,
    get_logout_use_case, get_refresh_token_use_case
)
from Application import RegisterService, LoginUseCase, LogOutUseCase, RefreshTokenUseCase

router = APIRouter(tags=["Authentication"])

INTERNAL_SERVER_ERROR_MSG = "Internal server error"


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED
)
async def register(
    user_data: UserRegister,
    register_service: Annotated[RegisterService, Depends(get_register_service)]
):
    try:
        # Call service to handle logic with dict unpacking
        user = await register_service.execute(**user_data.model_dump())
        return user
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        # Catch unexpected system errors
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )


@router.post("/login", response_model=TokenResponse)
async def login(
    login_data: UserLogin,
    response: Response,
    login_use_case: Annotated[LoginUseCase, Depends(get_login_use_case)]
):
    try:
        access_token, refresh_token, user = await login_use_case.execute(
            **login_data.model_dump()
        )
        
        # Set HttpOnly cookies
        response.set_cookie(
            key="access_token",
            value=access_token,
            httponly=True,
            secure=False, # Set to True in production with HTTPS
            samesite="lax",
            max_age=15 * 60 # 15 minutes
        )
        response.set_cookie(
            key="refresh_token",
            value=refresh_token,
            httponly=True,
            secure=False,
            samesite="lax",
            max_age=7 * 24 * 60 * 60 # 7 days
        )
        
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "user": user
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e)
        )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=INTERNAL_SERVER_ERROR_MSG
        )


@router.post("/logout")
async def logout(
    logout_data: LogoutRequest,
    response: Response,
    logout_use_case: Annotated[LogOutUseCase, Depends(get_logout_use_case)],
    refresh_token: Annotated[str | None, Cookie()] = None
):
    try:
        token_to_use = logout_data.refresh_token or refresh_token
        if not token_to_use:
            raise ValueError("No refresh token provided")
            
        await logout_use_case.execute(
            refresh_token_value=token_to_use,
            user_id=None,  # Need to integrate Get Current User to get the actual user_id
            logout_all_devices=logout_data.logout_all_devices
        )
        
        # Clear cookies
        response.delete_cookie("access_token")
        response.delete_cookie("refresh_token")
        
        return {"success": True, "message": "Successfully logged out"}
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=INTERNAL_SERVER_ERROR_MSG
        )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    refresh_data: RefreshTokenRequest,
    response: Response,
    refresh_use_case: Annotated[RefreshTokenUseCase, Depends(get_refresh_token_use_case)],
    refresh_token_cookie: Annotated[str | None, Cookie(alias="refresh_token")] = None
):
    try:
        token_to_use = refresh_data.refresh_token or refresh_token_cookie
        if not token_to_use:
            raise ValueError("No refresh token provided")
            
        access_token, refresh_token, user = await refresh_use_case.execute(
            refresh_token_value=token_to_use
        )
        
        # Set new cookies
        response.set_cookie(
            key="access_token",
            value=access_token,
            httponly=True,
            secure=False,
            samesite="lax",
            max_age=15 * 60
        )
        response.set_cookie(
            key="refresh_token",
            value=refresh_token,
            httponly=True,
            secure=False,
            samesite="lax",
            max_age=7 * 24 * 60 * 60
        )
        
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "user": user
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e)
        )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=INTERNAL_SERVER_ERROR_MSG
        )
