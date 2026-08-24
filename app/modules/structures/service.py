from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.domain.models import Structure


def project_structures_query(project_id: UUID) -> Select[tuple[Structure]]:
    return (
        select(Structure)
        .where(Structure.project_id == project_id)
        .order_by(Structure.name, Structure.id)
    )


async def get_project_structure(
    session: AsyncSession, project_id: UUID, structure_id: UUID
) -> Structure | None:
    result = await session.scalars(
        select(Structure).where(
            Structure.id == structure_id,
            Structure.project_id == project_id,
        )
    )
    return result.one_or_none()


async def validate_parent(
    session: AsyncSession,
    project_id: UUID,
    parent_id: UUID | None,
    structure_id: UUID | None = None,
) -> None:
    if parent_id is None:
        return

    visited: set[UUID] = set()
    cursor: UUID | None = parent_id
    first = True
    while cursor is not None:
        if cursor == structure_id or cursor in visited:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Structure hierarchy cannot contain a cycle",
            )
        visited.add(cursor)
        row = (
            await session.execute(
                select(Structure.id, Structure.parent_id).where(
                    Structure.id == cursor,
                    Structure.project_id == project_id,
                )
            )
        ).one_or_none()
        if row is None:
            detail = "Parent structure not found" if first else "Invalid structure hierarchy"
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)
        cursor = row.parent_id
        first = False
