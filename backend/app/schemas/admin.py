from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr

from app.models.enums import UserRole, UserStatus


class AdminUserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    email: EmailStr
    role: UserRole
    status: UserStatus
    last_login_at: datetime | None
    created_at: datetime
    updated_at: datetime
    document_count: int = 0


class AdminUserListResponse(BaseModel):
    items: list[AdminUserResponse]
    total: int
    page: int
    page_size: int
    pages: int
    has_next: bool
    has_previous: bool


class UserStatusUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: UserStatus


class UserRoleUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: UserRole


class AdminSummaryResponse(BaseModel):
    total_users: int
    active_users: int
    disabled_users: int
    administrators: int
    normal_users: int
    active_documents: int
    deleted_documents: int
    active_grants: int


class AdminAccountChangeResponse(BaseModel):
    user: AdminUserResponse
    changed: bool
