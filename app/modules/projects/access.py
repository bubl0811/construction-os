from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.domain.models import Project, ProjectMember, ProjectRole, User


class ProjectPermission(StrEnum):
    READ = "read"
    MANAGE_MEMBERS = "manage_members"
    MANAGE_STRUCTURES = "manage_structures"
    MANAGE_DOCUMENTS = "manage_documents"
    MANAGE_CALCULATIONS = "manage_calculations"


ROLE_PERMISSIONS: dict[ProjectRole, frozenset[ProjectPermission]] = {
    ProjectRole.OWNER: frozenset(ProjectPermission),
    ProjectRole.ADMIN: frozenset(ProjectPermission),
    ProjectRole.PROJECT_MANAGER: frozenset(
        {
            ProjectPermission.READ,
            ProjectPermission.MANAGE_STRUCTURES,
            ProjectPermission.MANAGE_DOCUMENTS,
            ProjectPermission.MANAGE_CALCULATIONS,
        }
    ),
    ProjectRole.ENGINEER: frozenset(
        {
            ProjectPermission.READ,
            ProjectPermission.MANAGE_STRUCTURES,
            ProjectPermission.MANAGE_DOCUMENTS,
            ProjectPermission.MANAGE_CALCULATIONS,
        }
    ),
    ProjectRole.FOREMAN: frozenset(
        {
            ProjectPermission.READ,
            ProjectPermission.MANAGE_DOCUMENTS,
            ProjectPermission.MANAGE_CALCULATIONS,
        }
    ),
    ProjectRole.PROCUREMENT: frozenset({ProjectPermission.READ}),
    ProjectRole.ACCOUNTANT: frozenset({ProjectPermission.READ}),
    ProjectRole.VIEWER: frozenset({ProjectPermission.READ}),
}


@dataclass(frozen=True, slots=True)
class ProjectAccess:
    project: Project
    membership: ProjectMember


def role_has_permission(role: ProjectRole, permission: ProjectPermission) -> bool:
    return permission in ROLE_PERMISSIONS[role]


async def require_project_permission(
    session: AsyncSession,
    user: User,
    project_id: UUID,
    permission: ProjectPermission = ProjectPermission.READ,
) -> ProjectAccess:
    row = (
        await session.execute(
            select(Project, ProjectMember)
            .join(ProjectMember, ProjectMember.project_id == Project.id)
            .where(
                Project.id == project_id,
                Project.company_id == user.company_id,
                ProjectMember.user_id == user.id,
            )
        )
    ).one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    project, membership = row
    if not role_has_permission(membership.role, permission):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient project permissions",
        )
    return ProjectAccess(project=project, membership=membership)
