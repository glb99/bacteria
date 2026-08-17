"""Record which extractor wording produced a memory, on all three tables.

All three, because the column is on ``MemoryContent`` and a test asserts the
memory tables differ in their keys and nothing else. The first attempt put it on
proposals alone — an activated memory is a human's decision, so the extractor's
wording looked irrelevant once accepted. That test caught it, and it was right:
"which wording produced the memories a person actually accepted" is the
acceptance-rate question, and discarding the version at the moment of acceptance
is exactly where it would be lost.

Nullable on all three, which is both honest and safe. Rows written before this
have no version to backfill, and the ``remember`` tool has none to supply at all
— its schema is built in ``bacteria.agent``. Nullable is also what makes this
applicable to tables that already have rows, which is the failure this repository
keeps a note about: autogenerate will happily write ``ADD COLUMN ... NOT NULL``
with no default, and that fails outright against real data while passing on an
empty development database.

Revision ID: 09a68f10e5a5
Revises: b7c2a91f4d05
Create Date: 2026-08-17 18:09:57.247420
"""

from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "09a68f10e5a5"
down_revision: Union[str, None] = "b7c2a91f4d05"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLES = ("chat_memory_entry", "chat_memory_proposal", "chat_user_memory_entry")


def upgrade() -> None:
    for table in _TABLES:
        op.add_column(
            table,
            sa.Column("prompt_version", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        )


def downgrade() -> None:
    for table in reversed(_TABLES):
        op.drop_column(table, "prompt_version")
