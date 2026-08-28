"""a project may say how to test it.

Nullable, because a project that has not said is a real and permanent state:
the probe reports it as unavailable and never as passing.

Revision ID: 40c36b3efc61
Revises: 99da2a5e164f
Create Date: 2026-08-28 18:40:02.362147
"""

from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "40c36b3efc61"
down_revision: Union[str, None] = "99da2a5e164f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "architecture_project",
        sa.Column("test_command", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("architecture_project", "test_command")
