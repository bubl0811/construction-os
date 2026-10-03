from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.modules.auth.dependencies import CurrentUser, SessionDep
from app.modules.domain.models import AuditEvent, Document, DocumentPage, SheetRevision
from app.modules.projects.access import ProjectPermission, require_project_permission

router = APIRouter(prefix="/projects/{project_id}/documents", tags=["drawing revisions"])


class SheetRevisionCreate(BaseModel):
    page_number: int = Field(ge=1)
    drawing_code: str = Field(min_length=1, max_length=128, pattern=r".*\S.*")
    revision: str = Field(min_length=1, max_length=64, pattern=r".*\S.*")


class SheetRevisionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    project_id: UUID
    document_id: UUID
    page_number: int
    drawing_code: str
    revision: str
    status: str
    approved_by_id: UUID | None
    approved_at: datetime | None


@router.get("/sheets", response_model=list[SheetRevisionResponse])
async def list_sheet_revisions(
    project_id: UUID, session: SessionDep, current_user: CurrentUser
) -> list[SheetRevision]:
    await require_project_permission(session, current_user, project_id)
    return list(
        await session.scalars(
            select(SheetRevision)
            .where(SheetRevision.project_id == project_id)
            .order_by(SheetRevision.drawing_code, SheetRevision.created_at.desc())
        )
    )


@router.post("/{document_id}/sheets", response_model=SheetRevisionResponse, status_code=201)
async def register_sheet_revision(
    project_id: UUID,
    document_id: UUID,
    payload: SheetRevisionCreate,
    session: SessionDep,
    current_user: CurrentUser,
) -> SheetRevision:
    await require_project_permission(
        session, current_user, project_id, ProjectPermission.MANAGE_DOCUMENTS
    )
    page = await session.scalar(
        select(DocumentPage.id).where(
            DocumentPage.project_id == project_id,
            DocumentPage.document_id == document_id,
            DocumentPage.page_number == payload.page_number,
        )
    )
    if page is None:
        raise HTTPException(status_code=404, detail="Source page not found")
    sheet = SheetRevision(
        project_id=project_id,
        document_id=document_id,
        page_number=payload.page_number,
        drawing_code=payload.drawing_code.strip().upper(),
        revision=payload.revision.strip(),
        status="draft",
    )
    session.add(sheet)
    try:
        await session.flush()
        session.add(
            AuditEvent(
                project_id=project_id,
                actor_id=current_user.id,
                entity_type="sheet_revision",
                entity_id=sheet.id,
                action="registered",
                new_value={
                    "document_id": str(document_id),
                    "page": sheet.page_number,
                    "drawing_code": sheet.drawing_code,
                    "revision": sheet.revision,
                    "status": "draft",
                },
            )
        )
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=409, detail="Sheet or revision already registered"
        ) from None
    await session.refresh(sheet)
    return sheet


@router.post("/sheets/{sheet_id}/approve", response_model=SheetRevisionResponse)
async def approve_sheet_revision(
    project_id: UUID,
    sheet_id: UUID,
    session: SessionDep,
    current_user: CurrentUser,
) -> SheetRevision:
    # This permission locks the project row, serialising simultaneous approvals.
    await require_project_permission(
        session, current_user, project_id, ProjectPermission.APPROVE_DOCUMENTS
    )
    sheet = await session.scalar(
        select(SheetRevision)
        .where(SheetRevision.id == sheet_id, SheetRevision.project_id == project_id)
        .with_for_update()
    )
    if sheet is None:
        raise HTTPException(status_code=404, detail="Sheet revision not found")
    if sheet.status != "draft":
        raise HTTPException(status_code=409, detail="Only a draft revision can be approved")
    document = await session.get(Document, sheet.document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Source document not found")
    previous = list(
        await session.scalars(
            select(SheetRevision).where(
                SheetRevision.project_id == project_id,
                SheetRevision.drawing_code == sheet.drawing_code,
                SheetRevision.status == "current",
            )
        )
    )
    for older in previous:
        older.status = "archived"
        session.add(
            AuditEvent(
                project_id=project_id,
                actor_id=current_user.id,
                entity_type="sheet_revision",
                entity_id=older.id,
                action="superseded",
                old_value={"status": "current"},
                new_value={"status": "archived", "superseded_by": str(sheet.id)},
            )
        )
    # Flush archives before the partial unique index sees the new current row.
    await session.flush()
    sheet.status = "current"
    sheet.approved_by_id = current_user.id
    sheet.approved_at = datetime.now(UTC)
    session.add(
        AuditEvent(
            project_id=project_id,
            actor_id=current_user.id,
            entity_type="sheet_revision",
            entity_id=sheet.id,
            action="approved",
            old_value={"status": "draft"},
            new_value={"status": "current", "sha256": document.sha256, "revision": sheet.revision},
        )
    )
    await session.commit()
    await session.refresh(sheet)
    return sheet
