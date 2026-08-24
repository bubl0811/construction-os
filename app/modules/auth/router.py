from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select

from app.core.security import create_access_token, hash_password, verify_password
from app.modules.auth.dependencies import CurrentUser, SessionDep
from app.modules.auth.schemas import CurrentUserResponse, RegisterRequest, TokenResponse
from app.modules.domain.models import Company, CompanyRole, User

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest, session: SessionDep) -> TokenResponse:
    email = payload.email.lower()
    if await session.scalar(select(User.id).where(User.email == email)) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    company = Company(name=payload.company_name)
    session.add(company)
    await session.flush()
    user = User(
        company_id=company.id,
        email=email,
        full_name=payload.full_name,
        password_hash=hash_password(payload.password),
        company_role=CompanyRole.OWNER,
    )
    session.add(user)
    await session.commit()
    return TokenResponse(access_token=create_access_token(user.id))


@router.post("/token", response_model=TokenResponse)
async def login(
    form: Annotated[OAuth2PasswordRequestForm, Depends()], session: SessionDep
) -> TokenResponse:
    user = await session.scalar(select(User).where(User.email == form.username.lower()))
    if user is None or not user.is_active or not verify_password(form.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return TokenResponse(access_token=create_access_token(user.id))


@router.get("/me", response_model=CurrentUserResponse)
async def me(current_user: CurrentUser) -> User:
    return current_user
