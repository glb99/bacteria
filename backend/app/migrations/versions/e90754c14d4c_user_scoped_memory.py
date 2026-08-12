"""user scoped memory

Adds the table for memory belonging to a person rather than a conversation, for
the agent's ADR 0021.

A new table, so none of the traps the last three migrations hit apply: there are
no existing rows for a NOT NULL column to fail against, and nothing to backfill.
The absence of a backfill is itself the decision — every existing memory stays
session-scoped, because nothing recorded whether a fact was meant to outlive its
conversation and promoting them would widen a blast radius nobody chose.

No foreign key on ``user_id``. It is the authenticated principal, which this
schema owns no table for; ``chat_session.user_id`` already carries the same
identifier unconstrained, and adding a constraint here would invent an ownership
that does not exist.

Revision ID: e90754c14d4c
Revises: c4a7b2e91d38
Create Date: 2026-08-11 18:07:01.255326
"""

from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "e90754c14d4c"
down_revision: Union[str, None] = "c4a7b2e91d38"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "chat_user_memory_entry",
        sa.Column("user_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("key", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("source", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("value", sa.JSON(), nullable=True),
        sa.Column("reason", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("user_id", "key"),
    )


def downgrade() -> None:
    op.drop_table("chat_user_memory_entry")
