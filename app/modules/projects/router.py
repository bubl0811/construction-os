from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from sqlalchemy.exc import IntegrityError

from app.modules.auth.dependencies import CurrentUser, SessionDep
from app.modules.domain.models import AuditEvent, Project, ProjectMember, ProjectRole
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
async def get_project(
    project_id: UUID, session: SessionDep, current_user: CurrentUser
) -> Project:
    project = await get_accessible_project(session, current_user, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project
