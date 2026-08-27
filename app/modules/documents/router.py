from pathlib import Path
from typing import Annotated
from uuid import UUID, uuid4

from anyio import to_thread
from fastapi import APIRouter, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse

from app.core.config import get_settings
from app.modules.auth.dependencies import CurrentUser, SessionDep
from app.modules.documents.schemas import DocumentResponse
from app.modules.documents.service import (
    DocumentValidationError,
    document_storage_file,
    get_project_document,
    persist_pdf,
    project_documents_query,
    safe_document_name,
)
from app.modules.domain.models import AuditEvent, Document, DocumentPage
from app.modules.projects.access import ProjectPermission, require_project_permission

router = APIRouter(prefix="/projects/{project_id}/documents", tags=["documents"])


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
