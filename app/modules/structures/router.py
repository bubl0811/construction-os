from uuid import UUID

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy.exc import IntegrityError

from app.modules.auth.dependencies import CurrentUser, SessionDep
from app.modules.domain.models import AuditEvent, Structure
from app.modules.projects.access import ProjectPermission, require_project_permission
from app.modules.structures.schemas import StructureCreate, StructureResponse, StructureUpdate
from app.modules.structures.service import (
    get_project_structure,
    project_structures_query,
    validate_parent,
)

router = APIRouter(prefix="/projects/{project_id}/structures", tags=["structures"])


def _audit_value(structure: Structure) -> dict[str, str | None]:
    return {
        "name": structure.name,
        "structure_type": structure.structure_type,
        "parent_id": str(structure.parent_id) if structure.parent_id else None,
    }


async def _required_structure(
    session: SessionDep, project_id: UUID, structure_id: UUID
) -> Structure:
    structure = await get_project_structure(session, project_id, structure_id)
    if structure is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Structure not found")
    return structure


@router.post("", response_model=StructureResponse, status_code=status.HTTP_201_CREATED)
async def create_structure(
    project_id: UUID,
    payload: StructureCreate,
    session: SessionDep,
    current_user: CurrentUser,
) -> Structure:
    await require_project_permission(
        session, current_user, project_id, ProjectPermission.MANAGE_STRUCTURES
    )
    await validate_parent(session, project_id, payload.parent_id)
    structure = Structure(
        project_id=project_id,
        parent_id=payload.parent_id,
        name=payload.name,
        structure_type=payload.structure_type.value,
    )
    session.add(structure)
    await session.flush()
    session.add(
        AuditEvent(
            project_id=project_id,
            actor_id=current_user.id,
            entity_type="structure",
            entity_id=structure.id,
            action="created",
            new_value=_audit_value(structure),
        )
    )
    await session.commit()
    return structure


@router.get("", response_model=list[StructureResponse])
async def list_structures(
    project_id: UUID, session: SessionDep, current_user: CurrentUser
) -> list[Structure]:
    await require_project_permission(session, current_user, project_id)
    return list((await session.scalars(project_structures_query(project_id))).all())


@router.get("/{structure_id}", response_model=StructureResponse)
async def get_structure(
    project_id: UUID,
    structure_id: UUID,
    session: SessionDep,
    current_user: CurrentUser,
) -> Structure:
    await require_project_permission(session, current_user, project_id)
    return await _required_structure(session, project_id, structure_id)


@router.patch("/{structure_id}", response_model=StructureResponse)
async def update_structure(
    project_id: UUID,
    structure_id: UUID,
    payload: StructureUpdate,
    session: SessionDep,
    current_user: CurrentUser,
) -> Structure:
    await require_project_permission(
        session, current_user, project_id, ProjectPermission.MANAGE_STRUCTURES
    )
    structure = await _required_structure(session, project_id, structure_id)
    old_value = _audit_value(structure)
    if "parent_id" in payload.model_fields_set:
        await validate_parent(session, project_id, payload.parent_id, structure.id)
        structure.parent_id = payload.parent_id
    if payload.name is not None:
        structure.name = payload.name
    if payload.structure_type is not None:
        structure.structure_type = payload.structure_type.value

    new_value = _audit_value(structure)
    if new_value == old_value:
        return structure
    session.add(
        AuditEvent(
            project_id=project_id,
            actor_id=current_user.id,
            entity_type="structure",
            entity_id=structure.id,
            action="updated",
            old_value=old_value,
            new_value=new_value,
        )
    )
    await session.commit()
    return structure


@router.delete("/{structure_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_structure(
    project_id: UUID,
    structure_id: UUID,
    session: SessionDep,
    current_user: CurrentUser,
) -> Response:
    await require_project_permission(
        session, current_user, project_id, ProjectPermission.MANAGE_STRUCTURES
    )
    structure = await _required_structure(session, project_id, structure_id)
    audit_event = AuditEvent(
        project_id=project_id,
        actor_id=current_user.id,
        entity_type="structure",
        entity_id=structure.id,
        action="deleted",
        old_value=_audit_value(structure),
    )
    await session.delete(structure)
    session.add(audit_event)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Structure is referenced by project records and cannot be deleted",
        ) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)
