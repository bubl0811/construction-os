from enum import StrEnum
from typing import Any
from uuid import UUID

from sqlalchemy import Boolean, Enum, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ProjectRole(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    PROJECT_MANAGER = "project_manager"
    ENGINEER = "engineer"
    FOREMAN = "foreman"
    PROCUREMENT = "procurement"
    ACCOUNTANT = "accountant"
    VIEWER = "viewer"


class CompanyRole(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"


class ProjectOwnedMixin:
    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False
    )


class Company(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "companies"
    name: Mapped[str] = mapped_column(String(255), nullable=False)


class User(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "users"
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    company_role: Mapped[CompanyRole] = mapped_column(
        Enum(CompanyRole, name="company_role"), default=CompanyRole.MEMBER, nullable=False
    )


class Project(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "projects"
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    address: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (UniqueConstraint("company_id", "code"),)


class ProjectMember(Base, UUIDPrimaryKeyMixin, TimestampMixin, ProjectOwnedMixin):
    __tablename__ = "project_members"
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    role: Mapped[ProjectRole] = mapped_column(Enum(ProjectRole, name="project_role"))
    __table_args__ = (UniqueConstraint("project_id", "user_id"),)


class Structure(Base, UUIDPrimaryKeyMixin, TimestampMixin, ProjectOwnedMixin):
    __tablename__ = "structures"
    parent_id: Mapped[UUID | None] = mapped_column(ForeignKey("structures.id", ondelete="SET NULL"))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    structure_type: Mapped[str] = mapped_column(String(64), nullable=False)


class Document(Base, UUIDPrimaryKeyMixin, TimestampMixin, ProjectOwnedMixin):
    __tablename__ = "documents"
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(127), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)


class DocumentPage(Base, UUIDPrimaryKeyMixin, TimestampMixin, ProjectOwnedMixin):
    __tablename__ = "document_pages"
    document_id: Mapped[UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    extracted_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    __table_args__ = (UniqueConstraint("document_id", "page_number"),)


class Calculation(Base, UUIDPrimaryKeyMixin, TimestampMixin, ProjectOwnedMixin):
    __tablename__ = "calculations"
    calculation_type: Mapped[str] = mapped_column(String(64), nullable=False)
    formula_version: Mapped[str] = mapped_column(String(64), nullable=False)
    input_data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    result: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    sources: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    created_by_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))


class ProgressEntry(Base, UUIDPrimaryKeyMixin, TimestampMixin, ProjectOwnedMixin):
    __tablename__ = "progress_entries"
    structure_id: Mapped[UUID | None] = mapped_column(ForeignKey("structures.id"))
    description: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[float | None] = mapped_column(Numeric(18, 4))
    unit: Mapped[str | None] = mapped_column(String(32))


class Task(Base, UUIDPrimaryKeyMixin, TimestampMixin, ProjectOwnedMixin):
    __tablename__ = "tasks"
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="open", nullable=False)
    assignee_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class Material(Base, UUIDPrimaryKeyMixin, TimestampMixin, ProjectOwnedMixin):
    __tablename__ = "materials"
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    unit: Mapped[str] = mapped_column(String(32), nullable=False)


class MaterialRequirement(Base, UUIDPrimaryKeyMixin, TimestampMixin, ProjectOwnedMixin):
    __tablename__ = "material_requirements"
    material_id: Mapped[UUID] = mapped_column(ForeignKey("materials.id", ondelete="RESTRICT"))
    structure_id: Mapped[UUID | None] = mapped_column(ForeignKey("structures.id"))
    quantity: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)


class PurchaseRequest(Base, UUIDPrimaryKeyMixin, TimestampMixin, ProjectOwnedMixin):
    __tablename__ = "purchase_requests"
    status: Mapped[str] = mapped_column(String(32), default="draft", nullable=False)
    requested_by_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)


class Crew(Base, UUIDPrimaryKeyMixin, TimestampMixin, ProjectOwnedMixin):
    __tablename__ = "crews"
    name: Mapped[str] = mapped_column(String(255), nullable=False)


class Worker(Base, UUIDPrimaryKeyMixin, TimestampMixin, ProjectOwnedMixin):
    __tablename__ = "workers"
    crew_id: Mapped[UUID | None] = mapped_column(ForeignKey("crews.id", ondelete="SET NULL"))
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    trade: Mapped[str] = mapped_column(String(127), nullable=False)


class Photo(Base, UUIDPrimaryKeyMixin, TimestampMixin, ProjectOwnedMixin):
    __tablename__ = "photos"
    structure_id: Mapped[UUID | None] = mapped_column(ForeignKey("structures.id"))
    storage_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    caption: Mapped[str | None] = mapped_column(Text)


class AIConversation(Base, UUIDPrimaryKeyMixin, TimestampMixin, ProjectOwnedMixin):
    __tablename__ = "ai_conversations"
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    title: Mapped[str | None] = mapped_column(String(255))


class AIMessage(Base, UUIDPrimaryKeyMixin, TimestampMixin, ProjectOwnedMixin):
    __tablename__ = "ai_messages"
    conversation_id: Mapped[UUID] = mapped_column(
        ForeignKey("ai_conversations.id", ondelete="CASCADE")
    )
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tool_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


class AuditEvent(Base, UUIDPrimaryKeyMixin, TimestampMixin, ProjectOwnedMixin):
    __tablename__ = "audit_events"
    actor_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[UUID] = mapped_column(nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    old_value: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    new_value: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
