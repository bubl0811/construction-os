import pytest

from app.modules.domain.models import ProjectRole
from app.modules.projects.access import ProjectPermission, role_has_permission


@pytest.mark.parametrize("role", list(ProjectRole))
def test_every_project_role_can_read(role: ProjectRole) -> None:
    assert role_has_permission(role, ProjectPermission.READ)


@pytest.mark.parametrize("role", [ProjectRole.OWNER, ProjectRole.ADMIN])
def test_only_administrative_roles_manage_members(role: ProjectRole) -> None:
    assert role_has_permission(role, ProjectPermission.MANAGE_MEMBERS)


@pytest.mark.parametrize(
    "role",
    [
        ProjectRole.PROJECT_MANAGER,
        ProjectRole.ENGINEER,
        ProjectRole.FOREMAN,
        ProjectRole.PROCUREMENT,
        ProjectRole.ACCOUNTANT,
        ProjectRole.VIEWER,
    ],
)
def test_non_administrative_roles_cannot_manage_members(role: ProjectRole) -> None:
    assert not role_has_permission(role, ProjectPermission.MANAGE_MEMBERS)


@pytest.mark.parametrize(
    "role",
    [ProjectRole.OWNER, ProjectRole.ADMIN, ProjectRole.PROJECT_MANAGER, ProjectRole.ENGINEER],
)
def test_technical_roles_manage_structures(role: ProjectRole) -> None:
    assert role_has_permission(role, ProjectPermission.MANAGE_STRUCTURES)
