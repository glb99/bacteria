"""Close the judgments a reversal was supposed to replace.

``architecture/decisions.py`` handed :meth:`SqlGraphRepository.close` a row read
straight out of ``current``, whose ``recorded_until`` is ``None`` by definition.
Closing it assigned that ``None`` back over itself and reported success having
changed nothing, so every change of mind appended a contradicting judgment and
left the old one standing. Both were current; the reader saw whichever the
database returned second.

**This closes the older one, and only where the pair is unambiguous.** For each
``(user, subject, claim)`` holding both an ``is_a`` and an ``is_not_a`` at once,
the row with the later ``recorded_at`` is what the person last said, and the
earlier is what the code failed to close. ``closed_by`` is set to ``superseded``,
matching what the fixed code now writes — a judgment stated in another's place,
which is not a retraction.

Nothing is deleted, so ``believed_at`` still answers what was held before the
reversal. It could not before this ran: both rows came back, and the question had
no single answer.

Scoped to ``ontology LIKE 'architecture:%'``. The same call exists nowhere else,
and a migration that reached into somebody's personal memory to close rows on a
heuristic would be doing something this one is not.

Revision ID: f1a7c39be204
Revises: 40c36b3efc61
Create Date: 2026-08-29
"""

from typing import Sequence, Union

from alembic import op

revision: str = "f1a7c39be204"
down_revision: Union[str, None] = "40c36b3efc61"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# The pair is identified by (user, src, dst) rather than by the relation, since
# the contradiction is precisely that both relations exist for one pair. Ties on
# `recorded_at` are left alone: two judgments in the same instant give no ground
# to prefer either, and guessing would be the same class of error as the bug.
CLOSE_THE_OLDER = """
UPDATE graph_assertion AS stale
SET recorded_until = fresh.recorded_at,
    closed_by = 'superseded'
FROM graph_assertion AS fresh
WHERE stale.ontology LIKE 'architecture:%'
  AND fresh.ontology = stale.ontology
  AND fresh.user_id = stale.user_id
  AND fresh.src = stale.src
  AND fresh.dst = stale.dst
  AND stale.rel IN ('is_a', 'is_not_a')
  AND fresh.rel IN ('is_a', 'is_not_a')
  AND fresh.rel <> stale.rel
  AND stale.recorded_until IS NULL
  AND fresh.recorded_until IS NULL
  AND fresh.recorded_at > stale.recorded_at
"""


def upgrade() -> None:
    op.execute(CLOSE_THE_OLDER)


def downgrade() -> None:
    """Deliberately empty.

    Reopening these would restore a contradiction, and the rows carry no mark
    distinguishing one this migration closed from one the fixed code closed
    honestly a minute later. Recreating the broken state is not worth being able
    to tell those apart.
    """
