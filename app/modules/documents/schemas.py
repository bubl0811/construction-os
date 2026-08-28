from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    name: str
    mime_type: str
    sha256: str
    page_count: int
    created_at: datetime
    updated_at: datetime


class DocumentUploadSessionResponse(BaseModel):
    upload_url: str
    token: str
    expires_in_seconds: int
    max_size_mb: int
