from uuid import uuid4

from sqlalchemy.dialects import postgresql

from app.modules.domain.models import CompanyRole, User
from app.modules.projects.service import accessible_projects_query


def test_accessible_projects_query_filters_company_and_membership() -> None:
    user = User(
        id=uuid4(),
        company_id=uuid4(),
        email="engineer@example.com",
        full_name="Test Engineer",
        password_hash="unused",
        company_role=CompanyRole.MEMBER,
    )
    query = str(
        accessible_projects_query(user).compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )
    assert str(user.company_id) in query
    assert str(user.id) in query
    assert "projects.company_id" in query
    assert "project_members.user_id" in query
