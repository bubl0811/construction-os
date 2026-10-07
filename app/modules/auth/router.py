from typing import Annotated

from anyio import to_thread
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.core.rate_limit import enforce_rate_limit
from app.core.security import create_access_token, hash_password, verify_password
from app.modules.auth.dependencies import CurrentUser, SessionDep
from app.modules.auth.schemas import (
    ChangePasswordRequest,
    CurrentUserResponse,
    RegisterRequest,
    TokenResponse,
)
from app.modules.domain.models import AccountAuditEvent, Company, CompanyRole, User

router = APIRouter(prefix="/auth", tags=["auth"])
DUMMY_PASSWORD_HASH = hash_password("not-a-real-account-password")


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest, session: SessionDep) -> TokenResponse:
    email = payload.email.lower()
    await enforce_rate_limit("register-email", email, 3, 3600)
    if await session.scalar(select(User.id).where(User.email == email)) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    company = Company(name=payload.company_name)
    session.add(company)
    await session.flush()
    user = User(
        company_id=company.id,
        email=email,
        full_name=payload.full_name,
        password_hash=await to_thread.run_sync(hash_password, payload.password),
        company_role=CompanyRole.OWNER,
    )
    session.add(user)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status_code=409, detail="Email already registered") from None
    return TokenResponse(access_token=create_access_token(user.id, user.auth_version))


@router.post("/token", response_model=TokenResponse)
async def login(
    form: Annotated[OAuth2PasswordRequestForm, Depends()], session: SessionDep
) -> TokenResponse:
    if len(form.username) > 320 or len(form.password) > 128:
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    await enforce_rate_limit("login-email", form.username.lower(), 12, 300)
    user = await session.scalar(select(User).where(User.email == form.username.lower()))
    # Match the password work for nonexistent and inactive accounts.
    encoded = user.password_hash if user else DUMMY_PASSWORD_HASH
    valid = await to_thread.run_sync(verify_password, form.password, encoded)
    if user is None or not user.is_active or not valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return TokenResponse(access_token=create_access_token(user.id, user.auth_version))


@router.get("/me", response_model=CurrentUserResponse)
async def me(current_user: CurrentUser) -> User:
    return current_user


@router.post("/change-password", response_model=TokenResponse)
async def change_password(
    payload: ChangePasswordRequest, current_user: CurrentUser, session: SessionDep
) -> TokenResponse:
    await enforce_rate_limit("password-change", str(current_user.id), 5, 300)
    old_hash = current_user.password_hash
    if not await to_thread.run_sync(verify_password, payload.current_password, old_hash):
        raise HTTPException(status_code=400, detail="Incorrect current password")
    if payload.current_password == payload.new_password:
        raise HTTPException(status_code=400, detail="New password must differ")
    new_hash = await to_thread.run_sync(hash_password, payload.new_password)
    version = current_user.auth_version + 1
    changed = await session.execute(
        update(User)
        .where(User.id == current_user.id, User.password_hash == old_hash)
        .values(password_hash=new_hash, auth_version=version)
        .returning(User.id)
        .execution_options(synchronize_session=False)
    )
    if changed.scalar_one_or_none() is None:
        await session.rollback()
        raise HTTPException(status_code=409, detail="Password already changed; sign in again")
    session.add(
        AccountAuditEvent(
            company_id=current_user.company_id,
            actor_id=current_user.id,
            action="password_changed",
            old_value={"auth_version": version - 1},
            new_value={"auth_version": version},
        )
    )
    await session.commit()
    return TokenResponse(access_token=create_access_token(current_user.id, version))
