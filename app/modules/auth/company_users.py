from anyio import to_thread
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.exc import IntegrityError

from app.core.security import hash_password
from app.modules.auth.dependencies import CurrentUser, SessionDep
from app.modules.auth.schemas import CurrentUserResponse
from app.modules.domain.models import CompanyRole, User

router = APIRouter(prefix="/company/users", tags=["company users"])


class CompanyUserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=255)
    password: str = Field(min_length=12, max_length=128)


@router.post("", response_model=CurrentUserResponse, status_code=201)
async def create_company_user(
    payload: CompanyUserCreate, session: SessionDep, current_user: CurrentUser
) -> User:
    if current_user.company_role not in {CompanyRole.OWNER, CompanyRole.ADMIN}:
        raise HTTPException(status_code=403, detail="Only company administrators can create users")
    user = User(
        company_id=current_user.company_id,
        email=str(payload.email).lower(),
        full_name=payload.full_name.strip(),
        company_role=CompanyRole.MEMBER,
        password_hash=await to_thread.run_sync(hash_password, payload.password),
    )
    session.add(user)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status_code=409, detail="Email already registered") from None
    await session.refresh(user)
    # Return the created user, never a replacement token for the administrator.
    return user
