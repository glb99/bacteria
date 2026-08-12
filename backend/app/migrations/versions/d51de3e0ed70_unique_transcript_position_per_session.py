"""unique transcript position per session

Adds the constraint that makes a duplicate `seq` fail loudly instead of quietly
reordering a conversation.

Autogenerate produced only the `create_unique_constraint` line, and that alone
would fail on any database that has already served overlapping requests --
which is every database this bug had a chance to affect. `commit` computed the
next position from the current maximum without a lock, so two concurrent
commits both claimed it. That is now fixed in the repository with a row lock;
this migration has to cope with the rows written before it was.

Existing duplicates are renumbered rather than reported, because refusing to
migrate would leave an operator with a broken deployment and no path forward.
Only sessions that actually contain a collision are touched.

The renumbering orders by `(seq, id)`. The relative order of colliding rows is
genuinely unknown -- that is the bug -- so `id` is used as the tiebreak: it is
insertion order, which is the best available evidence of what happened first.
This does not recover the true order. It picks a defensible one and makes it
stable, which is the most that is available after the fact.

Revision ID: d51de3e0ed70
Revises: 8157b61436d6
Create Date: 2026-08-08 17:59:16.515115
"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "d51de3e0ed70"
down_revision: Union[str, None] = "8157b61436d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        text(
            """
            WITH renumbered AS (
                SELECT id,
                       ROW_NUMBER() OVER (
                           PARTITION BY session_id ORDER BY seq, id
                       ) - 1 AS position
                FROM chat_transcript_item
                WHERE session_id IN (
                    SELECT session_id
                    FROM chat_transcript_item
                    GROUP BY session_id, seq
                    HAVING COUNT(*) > 1
                )
            )
            UPDATE chat_transcript_item AS item
            SET seq = renumbered.position
            FROM renumbered
            WHERE item.id = renumbered.id
            """
        )
    )
    op.create_unique_constraint(
        "uq_transcript_session_seq", "chat_transcript_item", ["session_id", "seq"]
    )


def downgrade() -> None:
    """Drops the constraint only.

    The renumbering is not undone, and could not be: the original values were
    ambiguous duplicates, so there is nothing to restore them to.
    """
    op.drop_constraint("uq_transcript_session_seq", "chat_transcript_item", type_="unique")
