from typing import Optional
from uuid import UUID

from Domain.entities.user import UserRole
from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserBase(BaseModel):
    email: EmailStr
    role: UserRole = UserRole.PATIENT


class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)


class RegisterStaffRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)
    role: UserRole


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    is_active: Optional[bool] = None


class UserResponse(UserBase):
    id: UUID
    is_active: bool
    is_email_verified: bool
    is_profile_completed: bool

    model_config = ConfigDict(from_attributes=True)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserResponse

    model_config = ConfigDict(from_attributes=True)


class RefreshTokenRequest(BaseModel):
    refresh_token: Optional[str] = None


class LogoutRequest(BaseModel):
    refresh_token: Optional[str] = None
    logout_all_devices: bool = False


class MeResponse(BaseModel):
    id: UUID
    email: str
    role: UserRole
    is_active: bool
    created_at: str

    model_config = ConfigDict(from_attributes=True)
