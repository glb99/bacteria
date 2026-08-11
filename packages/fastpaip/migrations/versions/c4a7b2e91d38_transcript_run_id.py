"""transcript run id

Adds the column that ties a transcript item to the run that wrote it, for
bacteria's ADR 0018.

Nullable, unlike the last two columns this project added, and deliberately not
backfilled. `source` could be backfilled with `owner` because the value was
known -- the owner was the only entrance that existed. No run id was ever
written down, so there is nothing to recover: every existing row genuinely has
no answer, and a synthetic one would look like evidence.

Indexed rather than left bare. The column exists to answer "everything run X
produced", asked with a run id a caller quotes back from an API response, which
is a lookup and not a scan.

Revision ID: c4a7b2e91d38
Revises: 5bebf5a064b6
Create Date: 2026-08-11 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = 'c4a7b2e91d38'
down_revision: Union[str, None] = '5bebf5a064b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'chat_transcript_item',
        sa.Column('run_id', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    )
    op.create_index(
        op.f('ix_chat_transcript_item_run_id'), 'chat_transcript_item', ['run_id'], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_chat_transcript_item_run_id'), table_name='chat_transcript_item')
    op.drop_column('chat_transcript_item', 'run_id')
