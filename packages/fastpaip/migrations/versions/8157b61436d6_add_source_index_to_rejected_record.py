"""add source_index to rejected_record

Revision ID: 8157b61436d6
Revises: 0001_procrastinate
Create Date: 2026-08-07 13:46:11.419832
"""

from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = '8157b61436d6'
down_revision: Union[str, None] = '0001_procrastinate'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Autogenerate produced a bare NOT NULL column, which fails outright on any
    # table that already has rows -- there is no value to put in them.
    #
    # Added with a server default so existing rows get one, then the default is
    # dropped so new rows must supply the real index. Leaving the default in
    # place would silently store -1 for anything that forgot to set it, which
    # is the failure this column exists to prevent.
    #
    # -1 means "recorded before this column existed" and is deliberately not a
    # valid position, so it cannot be mistaken for one.
    op.add_column(
        "rejected_record",
        sa.Column("source_index", sa.Integer(), nullable=False, server_default="-1"),
    )
    op.alter_column("rejected_record", "source_index", server_default=None)


def downgrade() -> None:
    op.drop_column("rejected_record", "source_index")
