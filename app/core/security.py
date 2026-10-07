from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import jwt
from pwdlib import PasswordHash

from app.core.config import get_settings

password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, encoded_hash: str) -> bool:
    return password_hash.verify(password, encoded_hash)


def create_access_token(user_id: UUID, auth_version: int = 0) -> str:
    settings = get_settings()
    expires_at = datetime.now(UTC) + timedelta(minutes=settings.access_token_expire_minutes)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "exp": expires_at,
        "type": "access",
        "version": auth_version,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> UUID:
    settings = get_settings()
    payload = jwt.decode(
        token,
        settings.secret_key,
        algorithms=[settings.jwt_algorithm],
        options={"require": ["exp", "sub", "type"]},
    )
    if payload.get("type") != "access" or not isinstance(payload.get("sub"), str):
        raise jwt.InvalidTokenError("Invalid access token")
    return UUID(payload["sub"])


def create_document_upload_token(user_id: UUID, project_id: UUID) -> str:
    settings = get_settings()
    expires_at = datetime.now(UTC) + timedelta(
        minutes=settings.document_upload_token_expire_minutes
    )
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "project_id": str(project_id),
        "exp": expires_at,
        "type": "document_upload",
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def decode_document_upload_token(token: str, project_id: UUID) -> UUID:
    settings = get_settings()
    payload = jwt.decode(
        token,
        settings.secret_key,
        algorithms=[settings.jwt_algorithm],
        options={"require": ["exp", "sub", "type"]},
    )
    if (
        payload.get("type") != "document_upload"
        or not isinstance(payload.get("sub"), str)
        or payload.get("project_id") != str(project_id)
    ):
        raise jwt.InvalidTokenError("Invalid document upload token")
    return UUID(payload["sub"])


def access_token_version(token: str) -> int:
    settings = get_settings()
    payload = jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
    version = payload.get("version", 0)
    if type(version) is not int or version < 0:
        raise jwt.InvalidTokenError("Invalid session version")
    return version
