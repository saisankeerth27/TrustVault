from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


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
