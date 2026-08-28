"""Add engineering calculation workflow fields.

Revision ID: 20260828_02
Revises: 20260824_01
Create Date: 2026-08-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260828_02"
down_revision: str | None = "20260824_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("calculations")}
    if "structure_id" not in columns:
        op.add_column("calculations", sa.Column("structure_id", postgresql.UUID(as_uuid=True)))
    if "title" not in columns:
        op.add_column(
            "calculations",
            sa.Column("title", sa.String(length=255), nullable=False, server_default="Розрахунок"),
        )
        op.alter_column("calculations", "title", server_default=None)
    if "status" not in columns:
        op.add_column(
            "calculations",
            sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        )
        op.alter_column("calculations", "status", server_default=None)
    if "notes" not in columns:
        op.add_column("calculations", sa.Column("notes", sa.Text()))

    inspector = sa.inspect(bind)
    foreign_keys = {
        foreign_key.get("name") for foreign_key in inspector.get_foreign_keys("calculations")
    }
    if "fk_calculations_structure_id_structures" not in foreign_keys:
        op.create_foreign_key(
            "fk_calculations_structure_id_structures",
            "calculations",
            "structures",
            ["structure_id"],
            ["id"],
            ondelete="SET NULL",
        )
    indexes = {index["name"] for index in inspector.get_indexes("calculations")}
    if "ix_calculations_structure_id" not in indexes:
        op.create_index("ix_calculations_structure_id", "calculations", ["structure_id"])


def downgrade() -> None:
    op.drop_index("ix_calculations_structure_id", table_name="calculations")
    op.drop_constraint(
        "fk_calculations_structure_id_structures", "calculations", type_="foreignkey"
    )
    op.drop_column("calculations", "notes")
    op.drop_column("calculations", "status")
    op.drop_column("calculations", "title")
    op.drop_column("calculations", "structure_id")
