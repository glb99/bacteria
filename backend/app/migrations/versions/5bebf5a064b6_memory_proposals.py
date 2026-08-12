"""memory proposals

Adds the proposals table and the `source` column that makes a memory
attributable, for ADR 0017.

Autogenerate emitted `add_column(..., nullable=False)` with no default, which
fails against any table that already has rows -- the same trap as the
`source_index` migration. Every existing memory was written by the session's
owner, since that was the only entrance until now, so backfilling `owner` is not
a guess. The default is added and then dropped: it exists to fill the rows that
are already there, not to let future inserts omit a source.

Revision ID: 5bebf5a064b6
Revises: d51de3e0ed70
Create Date: 2026-08-08 20:33:32.024084
"""

from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "5bebf5a064b6"
down_revision: Union[str, None] = "d51de3e0ed70"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "chat_memory_proposal",
        sa.Column("session_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("source", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("key", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("value", sa.JSON(), nullable=True),
        sa.Column("reason", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["chat_session.session_id"],
        ),
        sa.PrimaryKeyConstraint("session_id", "source", "key"),
    )
    op.add_column(
        "chat_memory_entry",
        sa.Column(
            "source",
            sqlmodel.sql.sqltypes.AutoString(),
            nullable=False,
            server_default="owner",
        ),
    )
    # Dropped immediately: the default existed to backfill rows written before
    # this column did, and leaving it would let an insert that forgot to say
    # where a memory came from silently claim the owner wrote it.
    op.alter_column("chat_memory_entry", "source", server_default=None)


def downgrade() -> None:
    op.drop_column("chat_memory_entry", "source")
    op.drop_table("chat_memory_proposal")
