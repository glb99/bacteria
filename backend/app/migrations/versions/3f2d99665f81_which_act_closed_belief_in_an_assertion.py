"""which act closed belief in an assertion

Revision ID: 3f2d99665f81
Revises: 6885a8d19fd8
Create Date: 2026-08-25 18:45:55.204219
"""

from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "3f2d99665f81"
down_revision: Union[str, None] = "6885a8d19fd8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Nullable with no default and no backfill, because NULL already means what
    # it needs to mean: still believed. Every existing row is either believed or
    # was closed by `supersede`, and marking the second retrospectively would
    # claim to know which act closed it -- the exact thing this column exists
    # because nobody recorded.
    op.add_column(
        "graph_assertion", sa.Column("closed_by", sqlmodel.sql.sqltypes.AutoString(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("graph_assertion", "closed_by")
