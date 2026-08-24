from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.domain.models import Project, ProjectMember, User


def accessible_projects_query(user: User) -> Select[tuple[Project]]:
    return (
        select(Project)
        .join(ProjectMember, ProjectMember.project_id == Project.id)
        .where(Project.company_id == user.company_id, ProjectMember.user_id == user.id)
        .order_by(Project.name)
    )


async def get_accessible_project(
    session: AsyncSession, user: User, project_id: UUID
) -> Project | None:
    return await session.scalar(accessible_projects_query(user).where(Project.id == project_id))
