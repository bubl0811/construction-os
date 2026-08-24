from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr

from app.modules.domain.models import ProjectRole


class ProjectMemberCreate(BaseModel):
    email: EmailStr
    role: ProjectRole


class ProjectMemberUpdate(BaseModel):
    role: ProjectRole


class ProjectMemberResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    email: EmailStr
    full_name: str
    role: ProjectRole
