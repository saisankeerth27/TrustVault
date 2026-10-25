from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, SecretStr, field_validator

from app.core.security import validate_password_strength
from app.models.enums import UserRole, UserStatus


class RegisterRequest(BaseModel):
    """Public registration always creates a normal user account."""

    model_config = ConfigDict(extra="forbid")

    name: str
    email: EmailStr
    password: SecretStr

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Name must not be blank.")
        if len(stripped) > 255:
            raise ValueError("Name must be at most 255 characters.")
        return stripped

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        return str(value).strip().lower()

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: SecretStr) -> SecretStr:
        validate_password_strength(value.get_secret_value())
        return value


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: SecretStr

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        return str(value).strip().lower()


class PasswordRecoveryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        return str(value).strip().lower()


class PasswordRecoveryVerifyRequest(PasswordRecoveryRequest):
    token: str

    @field_validator("token")
    @classmethod
    def validate_recovery_token(cls, value: str) -> str:
        stripped = value.strip()
        if len(stripped) not in (6, 8) or not stripped.isascii() or not stripped.isdigit():
            raise ValueError("Enter the eight-digit verification code.")
        return stripped


class PasswordRecoveryUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    password: SecretStr

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: SecretStr) -> SecretStr:
        validate_password_strength(value.get_secret_value())
        return value


class OtpLoginRequest(BaseModel):
    """Email-only request to trigger a passwordless OTP sign-in."""

    model_config = ConfigDict(extra="forbid")

    email: EmailStr

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        return str(value).strip().lower()


class OtpVerifyRequest(BaseModel):
    """Email + OTP token to verify a passwordless sign-in or signup confirmation."""

    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    token: str

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        return str(value).strip().lower()

    @field_validator("token")
    @classmethod
    def validate_token(cls, value: str) -> str:
        stripped = value.strip()
        if len(stripped) != 8 or not stripped.isascii() or not stripped.isdigit():
            raise ValueError("Enter the eight-digit verification code.")
        return stripped

class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    email: EmailStr
    role: UserRole
    status: UserStatus
    created_at: datetime


class AuthResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
    user: UserResponse
