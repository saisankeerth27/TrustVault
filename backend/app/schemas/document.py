from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.models.enums import DocumentAccessLevel, PermissionLevel


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    owner_id: UUID
    owner_name: str
    name: str
    category: str | None
    description: str | None
    mime_type: str
    file_size: int
    checksum: str
    access_level: DocumentAccessLevel
    created_at: datetime
    updated_at: datetime


class DocumentListResponse(BaseModel):
    items: list[DocumentResponse]
    total: int
    page: int
    page_size: int
    pages: int
    has_next: bool
    has_previous: bool


class DocumentVersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    document_id: UUID
    version_number: int
    original_filename: str
    mime_type: str
    file_size: int
    checksum: str
    uploaded_by: UUID | None
    uploader_name: str
    change_summary: str | None
    is_current: bool
    created_at: datetime


class DocumentVersionListResponse(BaseModel):
    items: list[DocumentVersionResponse]
    total: int
    current_version_number: int | None


class DocumentVersionReplacementResponse(BaseModel):
    document: DocumentResponse
    version: DocumentVersionResponse


class DocumentContentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(max_length=10_000_000)
    expected_version_number: int = Field(ge=1)
    change_summary: str | None = Field(default=None, max_length=500)

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        if not value:
            raise ValueError("Document content must not be empty.")
        if "\x00" in value:
            raise ValueError("Document content contains invalid characters.")
        return value

    @field_validator("change_summary", mode="before")
    @classmethod
    def normalize_change_summary(cls, value: object) -> object:
        if value is None:
            return None
        if not isinstance(value, str):
            return value
        stripped = value.strip()
        if "\x00" in stripped:
            raise ValueError("Change summary contains invalid characters.")
        return stripped or None


class DocumentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, max_length=255)
    category: str | None = Field(default=None, max_length=100)
    description: str | None = Field(default=None, max_length=2000)

    @field_validator("name", mode="before")
    @classmethod
    def normalize_name(cls, value: object) -> object:
        if value is None:
            return value
        if not isinstance(value, str):
            return value
        stripped = value.strip()
        if not stripped:
            raise ValueError("Document name must not be blank.")
        if any(ord(character) < 32 or ord(character) == 127 for character in stripped):
            raise ValueError("Document name contains invalid characters.")
        return stripped

    @field_validator("category", mode="before")
    @classmethod
    def normalize_category(cls, value: object) -> object:
        if value is None:
            return None
        if not isinstance(value, str):
            return value
        stripped = value.strip()
        if any(ord(character) < 32 or ord(character) == 127 for character in stripped):
            raise ValueError("Category contains invalid characters.")
        return stripped or None

    @field_validator("description", mode="before")
    @classmethod
    def normalize_description(cls, value: object) -> object:
        if value is None:
            return None
        if not isinstance(value, str):
            return value
        stripped = value.strip()
        if "\x00" in stripped:
            raise ValueError("Description contains invalid characters.")
        return stripped or None

    @model_validator(mode="after")
    def require_at_least_one_update(self) -> "DocumentUpdate":
        if not self.model_fields_set:
            raise ValueError("At least one metadata field must be provided.")
        if "name" in self.model_fields_set and self.name is None:
            raise ValueError("Document name must not be null.")
        return self


class PermissionGrantRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    permission: PermissionLevel

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        return str(value).strip().lower()


class PermissionUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    permission: PermissionLevel


class PermissionResponse(BaseModel):
    id: UUID
    document_id: UUID
    user_id: UUID
    recipient_name: str
    recipient_email: EmailStr
    permission: PermissionLevel
    granted_at: datetime
    revoked_at: datetime | None
    status: Literal["ACTIVE", "REVOKED"]


class PermissionListResponse(BaseModel):
    items: list[PermissionResponse]
    total: int
    active_total: int
