"""Audit password changes and revoke previous sessions."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261007_04"
down_revision: str | None = "20261003_03"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # The initial migration uses live metadata; support both new and existing databases.
    inspector = sa.inspect(op.get_bind())
    if "auth_version" not in {column["name"] for column in inspector.get_columns("users")}:
        op.add_column(
            "users", sa.Column("auth_version", sa.Integer(), server_default="0", nullable=False)
        )
    if not inspector.has_table("account_audit_events"):
        op.create_table(
            "account_audit_events",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column(
                "company_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("companies.id", ondelete="RESTRICT"),
                nullable=False,
            ),
            sa.Column(
                "actor_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("users.id", ondelete="RESTRICT"),
                nullable=False,
            ),
            sa.Column("action", sa.String(64), nullable=False),
            sa.Column("old_value", postgresql.JSONB(), nullable=False),
            sa.Column("new_value", postgresql.JSONB(), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
        )


def downgrade() -> None:
    op.drop_table("account_audit_events")
    op.drop_column("users", "auth_version")
