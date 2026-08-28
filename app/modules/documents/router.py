from pathlib import Path
from typing import Annotated
from uuid import UUID, uuid4

import jwt
from anyio import to_thread
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import get_settings
from app.core.security import create_document_upload_token, decode_document_upload_token
from app.modules.auth.dependencies import CurrentUser, SessionDep
from app.modules.documents.schemas import DocumentResponse, DocumentUploadSessionResponse
from app.modules.documents.service import (
    DocumentValidationError,
    document_storage_file,
    get_project_document,
    persist_pdf,
    project_documents_query,
    safe_document_name,
)
from app.modules.domain.models import AuditEvent, Document, DocumentPage, User
from app.modules.projects.access import ProjectPermission, require_project_permission

router = APIRouter(prefix="/projects/{project_id}/documents", tags=["documents"])
upload_token_scheme = HTTPBearer()


def _response(document: Document, page_count: int) -> DocumentResponse:
    return DocumentResponse(
        id=document.id,
        project_id=document.project_id,
        name=document.name,
        mime_type=document.mime_type,
        sha256=document.sha256,
        page_count=page_count,
        created_at=document.created_at,
        updated_at=document.updated_at,
    )


async def _store_document(
    project_id: UUID,
    session: SessionDep,
    current_user: CurrentUser,
    file: Annotated[UploadFile, File()],
) -> DocumentResponse:
    settings = get_settings()
    document_id = uuid4()
    storage_key = f"{project_id}/{document_id}.pdf"
    final_path = document_storage_file(settings.document_storage_path, storage_key)
    temporary_path = final_path.with_suffix(".upload")

    try:
        sha256, page_count = await to_thread.run_sync(
            persist_pdf,
            file.file,
            temporary_path,
            final_path,
            settings.max_document_size_mb * 1024 * 1024,
        )
    except DocumentValidationError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)
        ) from None
    finally:
        await file.close()

    document = Document(
        id=document_id,
        project_id=project_id,
        name=safe_document_name(file.filename),
        storage_key=storage_key,
        mime_type="application/pdf",
        sha256=sha256,
    )
    session.add(document)
    session.add_all(
        DocumentPage(project_id=project_id, document_id=document.id, page_number=page_number)
        for page_number in range(1, page_count + 1)
    )
    session.add(
        AuditEvent(
            project_id=project_id,
            actor_id=current_user.id,
            entity_type="document",
            entity_id=document.id,
            action="uploaded",
            new_value={
                "name": document.name,
                "mime_type": document.mime_type,
                "sha256": document.sha256,
                "page_count": page_count,
            },
        )
    )
    try:
        await session.commit()
    except Exception:
        await session.rollback()
        final_path.unlink(missing_ok=True)
        raise
    await session.refresh(document)
    return _response(document, page_count)


@router.post("", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    project_id: UUID,
    session: SessionDep,
    current_user: CurrentUser,
    file: Annotated[UploadFile, File()],
) -> DocumentResponse:
    await require_project_permission(
        session, current_user, project_id, ProjectPermission.MANAGE_DOCUMENTS
    )
    return await _store_document(project_id, session, current_user, file)


@router.post("/upload-session", response_model=DocumentUploadSessionResponse)
async def create_upload_session(
    project_id: UUID,
    session: SessionDep,
    current_user: CurrentUser,
) -> DocumentUploadSessionResponse:
    await require_project_permission(
        session, current_user, project_id, ProjectPermission.MANAGE_DOCUMENTS
    )
    settings = get_settings()
    return DocumentUploadSessionResponse(
        upload_url=f"{settings.public_api_url.rstrip('/')}/projects/{project_id}/documents/direct-upload",
        token=create_document_upload_token(current_user.id, project_id),
        expires_in_seconds=settings.document_upload_token_expire_minutes * 60,
        max_size_mb=settings.max_document_size_mb,
    )


@router.post(
    "/direct-upload",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def direct_upload_document(
    project_id: UUID,
    session: SessionDep,
    file: Annotated[UploadFile, File()],
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(upload_token_scheme)],
) -> DocumentResponse:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired document upload token",
    )
    try:
        user_id = decode_document_upload_token(credentials.credentials, project_id)
    except (jwt.InvalidTokenError, ValueError):
        raise unauthorized from None
    current_user = await session.get(User, user_id)
    if current_user is None or not current_user.is_active:
        raise unauthorized
    await require_project_permission(
        session, current_user, project_id, ProjectPermission.MANAGE_DOCUMENTS
    )
    return await _store_document(project_id, session, current_user, file)


@router.get("", response_model=list[DocumentResponse])
async def list_documents(
    project_id: UUID, session: SessionDep, current_user: CurrentUser
) -> list[DocumentResponse]:
    await require_project_permission(session, current_user, project_id)
    rows = (await session.execute(project_documents_query(project_id))).all()
    return [_response(document, page_count) for document, page_count in rows]


@router.get("/{document_id}/download")
async def download_document(
    project_id: UUID,
    document_id: UUID,
    session: SessionDep,
    current_user: CurrentUser,
) -> FileResponse:
    await require_project_permission(session, current_user, project_id)
    document = await get_project_document(session, project_id, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    path = document_storage_file(get_settings().document_storage_path, document.storage_key)
    if not path.is_file():
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Document file is missing from storage",
        )
    return FileResponse(path=Path(path), media_type=document.mime_type, filename=document.name)
