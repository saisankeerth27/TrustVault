from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    owner_id: UUID
    name: str
    category: str | None
    description: str | None
    mime_type: str
    file_size: int
    checksum: str
    created_at: datetime
    updated_at: datetime
