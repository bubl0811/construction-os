import app.modules.domain  # noqa: F401
from app.db.base import Base


def test_all_required_domain_tables_are_registered() -> None:
    expected = {
        "companies", "users", "projects", "project_members", "structures", "documents",
        "document_pages", "calculations", "progress_entries", "tasks", "materials",
        "material_requirements", "purchase_requests", "workers", "crews", "photos",
        "ai_conversations", "ai_messages", "audit_events",
    }
    assert expected <= set(Base.metadata.tables)


def test_project_owned_tables_have_project_id() -> None:
    exceptions = {"companies", "users", "projects"}
    for table_name in set(Base.metadata.tables) - exceptions:
        assert "project_id" in Base.metadata.tables[table_name].columns
