from uuid import UUID

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.config import get_settings
from app.modules.auth.dependencies import CurrentUser, SessionDep
from app.modules.documents.service import document_storage_file
from app.modules.domain.models import AuditEvent, Document, Project, ProjectMember, ProjectRole
from app.modules.projects.access import ProjectPermission, require_project_permission
from app.modules.projects.schemas import ProjectCreate, ProjectResponse
from app.modules.projects.service import accessible_projects_query, get_accessible_project

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    payload: ProjectCreate, session: SessionDep, current_user: CurrentUser
) -> Project:
    project = Project(
        company_id=current_user.company_id,
        name=payload.name,
        code=payload.code.upper(),
        address=payload.address,
    )
    session.add(project)
    try:
        await session.flush()
        session.add(
            ProjectMember(project_id=project.id, user_id=current_user.id, role=ProjectRole.OWNER)
        )
        session.add(
            AuditEvent(
                project_id=project.id,
                actor_id=current_user.id,
                entity_type="project",
                entity_id=project.id,
                action="created",
                new_value={
                    "name": project.name,
                    "code": project.code,
                    "address": project.address,
                },
            )
        )
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Project code already exists in this company",
        ) from None
    return project


@router.get("", response_model=list[ProjectResponse])
async def list_projects(session: SessionDep, current_user: CurrentUser) -> list[Project]:
    return list((await session.scalars(accessible_projects_query(current_user))).all())


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(project_id: UUID, session: SessionDep, current_user: CurrentUser) -> Project:
    project = await get_accessible_project(session, current_user, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


class ProjectDeleteRequest(BaseModel):
    confirmation_code: str = Field(min_length=1, max_length=64)


@router.get("/{project_id}/permissions")
async def project_permissions(
    project_id: UUID, session: SessionDep, current_user: CurrentUser
) -> dict[str, bool]:
    access = await require_project_permission(session, current_user, project_id)
    return {"can_delete": access.membership.role == ProjectRole.OWNER}


@router.delete("/{project_id}", status_code=204)
async def delete_project(
    project_id: UUID, payload: ProjectDeleteRequest, session: SessionDep, current_user: CurrentUser
) -> Response:
    access = await require_project_permission(
        session, current_user, project_id, ProjectPermission.MANAGE_MEMBERS
    )
    if access.membership.role != ProjectRole.OWNER:
        raise HTTPException(status_code=403, detail="Only the project owner can delete it")
    if payload.confirmation_code != access.project.code:
        raise HTTPException(status_code=422, detail="Project confirmation code does not match")
    keys = list(
        await session.scalars(select(Document.storage_key).where(Document.project_id == project_id))
    )
    root = get_settings().document_storage_path
    # Validate paths before deleting anything. Never accept a client-supplied path.
    files = [document_storage_file(root, key) for key in keys]
    await session.delete(access.project)
    await session.commit()
    # Database cascades remove membership and all project-owned records.
    # Orphan cleanup failures must not turn a committed deletion into a retry.
    import logging

    for file in files:
        try:
            file.unlink(missing_ok=True)
        except OSError:
            logging.getLogger(__name__).error("Deleted project has a file pending cleanup")
    return Response(status_code=204)
