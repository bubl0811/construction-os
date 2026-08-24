from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.modules.domain.models import CompanyRole


class RegisterRequest(BaseModel):
    company_name: str = Field(min_length=2, max_length=255)
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=255)
    password: str = Field(min_length=12, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class CurrentUserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_id: UUID
    email: EmailStr
    full_name: str
    company_role: CompanyRole
