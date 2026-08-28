"""The codebases this deployment has been pointed at.

A new table with no existing rows, so the NOT NULL columns are safe here in a
way autogenerate cannot promise in general.

Revision ID: a02f2941059b
Revises: 9ff8d83f57bf
Create Date: 2026-08-28 17:16:15.874075
"""

from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "a02f2941059b"
down_revision: Union[str, None] = "9ff8d83f57bf"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "architecture_project",
        sa.Column("project_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("principal_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("location", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("added_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("project_id"),
    )
    op.create_index(
        op.f("ix_architecture_project_principal_id"),
        "architecture_project",
        ["principal_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_architecture_project_principal_id"), table_name="architecture_project")
    op.drop_table("architecture_project")
