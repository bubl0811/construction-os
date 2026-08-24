"""Create the initial project-centric schema.

Revision ID: 20260824_01
Revises:
Create Date: 2026-08-24
"""

from collections.abc import Sequence

from alembic import op

import app.modules.domain  # noqa: F401
from app.db.base import Base

revision: str = "20260824_01"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind(), checkfirst=False)


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind(), checkfirst=False)
