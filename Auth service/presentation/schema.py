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
    full_name: Optional[str] = None


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    is_active: Optional[bool] = None


class UserResponse(UserBase):
    id: UUID
    full_name: Optional[str] = None
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


class VerifyEmailRequest(BaseModel):
    email: EmailStr
    otp: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$")


class ResendOTPRequest(BaseModel):
    email: EmailStr


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    email: EmailStr
    otp: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$")
    new_password: str = Field(..., min_length=8)


# ── Admin schemas ─────────────────────────────────────────────────────────────

class SystemConfigResponse(BaseModel):
    clinic_name: str
    maintenance_mode: bool
    default_slot_duration_minutes: int
    max_appointments_per_day: int
    support_email: Optional[str] = None
    working_hours_start: str
    working_hours_end: str
    updated_at: Optional[str] = None
    updated_by: Optional[str] = None


class SystemConfigUpdate(BaseModel):
    clinic_name: Optional[str] = None
    maintenance_mode: Optional[bool] = None
    default_slot_duration_minutes: Optional[int] = None
    max_appointments_per_day: Optional[int] = None
    support_email: Optional[str] = None
    working_hours_start: Optional[str] = Field(
        default=None, description="HH:MM", pattern=r"^\d{2}:\d{2}$"
    )
    working_hours_end: Optional[str] = Field(
        default=None, description="HH:MM", pattern=r"^\d{2}:\d{2}$"
    )


class UserAdminResponse(BaseModel):
    id: str
    email: str
    full_name: Optional[str] = None
    role: str
    is_active: bool
    is_email_verified: bool
    is_profile_completed: bool
    created_at: Optional[str] = None


class UserStatusUpdate(BaseModel):
    is_active: bool


class UserAdminUpdate(BaseModel):
    full_name: Optional[str] = None
    email: Optional[EmailStr] = None
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None


class NotificationSettingsItem(BaseModel):
    key: str
    title: str
    sub: str
    enabled: bool


class NotificationSettingsUpdate(BaseModel):
    settings: list[dict]


class NotificationSettingsResponse(BaseModel):
    settings: Optional[list[dict]] = None
    updated_at: Optional[str] = None
    updated_by: Optional[str] = None


class SecuritySettingsResponse(BaseModel):
    two_factor: bool = False
    session_timeout_minutes: int = 30
    login_attempt_limit: int = 5
    audit_log: bool = True
    password_rules: list[dict] = []
    updated_at: Optional[str] = None
    updated_by: Optional[str] = None


class SecuritySettingsUpdate(BaseModel):
    two_factor: Optional[bool] = None
    session_timeout_minutes: Optional[int] = None
    login_attempt_limit: Optional[int] = None
    audit_log: Optional[bool] = None
    password_rules: Optional[list[dict]] = None
