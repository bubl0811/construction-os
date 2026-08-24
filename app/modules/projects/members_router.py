from uuid import UUID

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.modules.auth.dependencies import CurrentUser, SessionDep
from app.modules.domain.models import AuditEvent, ProjectMember, ProjectRole, User
from app.modules.projects.access import ProjectPermission, require_project_permission
from app.modules.projects.member_schemas import (
    ProjectMemberCreate,
    ProjectMemberResponse,
    ProjectMemberUpdate,
)

router = APIRouter(prefix="/projects/{project_id}/members", tags=["project members"])


def _member_response(member: ProjectMember, user: User) -> ProjectMemberResponse:
    return ProjectMemberResponse(
        id=member.id,
        user_id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=member.role,
    )


async def _get_member(
    session: SessionDep, project_id: UUID, member_id: UUID
) -> tuple[ProjectMember, User]:
    row = (
        await session.execute(
            select(ProjectMember, User)
            .join(User, User.id == ProjectMember.user_id)
            .where(ProjectMember.id == member_id, ProjectMember.project_id == project_id)
        )
    ).one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")
    return row


def _require_owner_for_owner_change(actor_role: ProjectRole, target_role: ProjectRole) -> None:
    if target_role == ProjectRole.OWNER and actor_role != ProjectRole.OWNER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only a project owner can manage owners",
        )


async def _ensure_not_last_owner(
    session: SessionDep, project_id: UUID, member: ProjectMember
) -> None:
    if member.role != ProjectRole.OWNER:
        return
    owner_count = await session.scalar(
        select(func.count(ProjectMember.id)).where(
            ProjectMember.project_id == project_id,
            ProjectMember.role == ProjectRole.OWNER,
        )
    )
    if owner_count == 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A project must have at least one owner",
        )


@router.get("", response_model=list[ProjectMemberResponse])
async def list_project_members(
    project_id: UUID, session: SessionDep, current_user: CurrentUser
) -> list[ProjectMemberResponse]:
    await require_project_permission(session, current_user, project_id)
    rows = (
        await session.execute(
            select(ProjectMember, User)
            .join(User, User.id == ProjectMember.user_id)
            .where(ProjectMember.project_id == project_id)
            .order_by(User.full_name, User.email)
        )
    ).all()
    return [_member_response(member, user) for member, user in rows]


@router.post("", response_model=ProjectMemberResponse, status_code=status.HTTP_201_CREATED)
async def add_project_member(
    project_id: UUID,
    payload: ProjectMemberCreate,
    session: SessionDep,
    current_user: CurrentUser,
) -> ProjectMemberResponse:
    access = await require_project_permission(
        session, current_user, project_id, ProjectPermission.MANAGE_MEMBERS
    )
    _require_owner_for_owner_change(access.membership.role, payload.role)
    user = await session.scalar(
        select(User).where(
            User.company_id == current_user.company_id,
            User.email == payload.email.lower(),
            User.is_active.is_(True),
        )
    )
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Active user not found in this company",
        )

    member = ProjectMember(project_id=project_id, user_id=user.id, role=payload.role)
    session.add(member)
    try:
        await session.flush()
        session.add(
            AuditEvent(
                project_id=project_id,
                actor_id=current_user.id,
                entity_type="project_member",
                entity_id=member.id,
                action="created",
                new_value={"user_id": str(user.id), "role": member.role.value},
            )
        )
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User is already a project member",
        ) from None
    return _member_response(member, user)


@router.patch("/{member_id}", response_model=ProjectMemberResponse)
async def update_project_member(
    project_id: UUID,
    member_id: UUID,
    payload: ProjectMemberUpdate,
    session: SessionDep,
    current_user: CurrentUser,
) -> ProjectMemberResponse:
    access = await require_project_permission(
        session, current_user, project_id, ProjectPermission.MANAGE_MEMBERS
    )
    member, user = await _get_member(session, project_id, member_id)
    _require_owner_for_owner_change(access.membership.role, member.role)
    _require_owner_for_owner_change(access.membership.role, payload.role)
    if member.role == ProjectRole.OWNER and payload.role != ProjectRole.OWNER:
        await _ensure_not_last_owner(session, project_id, member)

    old_role = member.role
    if old_role == payload.role:
        return _member_response(member, user)
    member.role = payload.role
    session.add(
        AuditEvent(
            project_id=project_id,
            actor_id=current_user.id,
            entity_type="project_member",
            entity_id=member.id,
            action="role_changed",
            old_value={"role": old_role.value},
            new_value={"role": member.role.value},
        )
    )
    await session.commit()
    return _member_response(member, user)


@router.delete("/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_project_member(
    project_id: UUID,
    member_id: UUID,
    session: SessionDep,
    current_user: CurrentUser,
) -> Response:
    access = await require_project_permission(
        session, current_user, project_id, ProjectPermission.MANAGE_MEMBERS
    )
    member, _ = await _get_member(session, project_id, member_id)
    _require_owner_for_owner_change(access.membership.role, member.role)
    await _ensure_not_last_owner(session, project_id, member)
    old_value = {"user_id": str(member.user_id), "role": member.role.value}
    audit_event = AuditEvent(
        project_id=project_id,
        actor_id=current_user.id,
        entity_type="project_member",
        entity_id=member.id,
        action="deleted",
        old_value=old_value,
    )
    await session.delete(member)
    session.add(audit_event)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
