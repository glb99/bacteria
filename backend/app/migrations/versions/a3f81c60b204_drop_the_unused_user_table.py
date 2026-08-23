"""Drop the ``user`` table, which nothing ever read.

Template scaffolding, created by `600342e2f3c5` on the day the study project was
frozen and never wired to anything: no router mounted its repository, no feature
imported its model, and no row was ever written outside its own tests.

**It is not the accounts table, and its name was the problem.** Every identity in
this application is a bare ``principal_id`` string -- on ``api_key``,
``browser_session``, ``chat_session.user_id`` and ``user_memory.user_id`` -- with
no foreign key to anything, deliberately, because the agent must not depend on a
feature it knows nothing about. This table held an autoincrement ``id``, a
``name`` and an ``email``, none of which any credential resolves to. A reader
following authentication code found a table called ``user`` that looked like the
answer and was not related to it at all. See
`docs/adr/0004-authentication-is-shared-authorization-lives-next-to-the-resource.md`
and `docs/adr/0005-a-browser-holds-a-session-not-a-key.md`, which both state
there is no accounts table -- true in every sense except this one.

`600342e2f3c5` is left in the history rather than removed. It has been applied to
the deployed database since before this repository had a deployment, so editing
it out would leave production holding a table no migration mentions and a
`down_revision` chain that no longer matches `alembic_version`. Dropping forward
is the only version that works on a database that already ran the original.

Safe on a database with rows in it, in the only sense that matters here: the drop
destroys whatever the table holds, and what it holds is nothing. Verified against
the development database, which had zero rows -- the tests truncate it, and
nothing else ever inserted.

Reversible. ``downgrade`` recreates the table exactly as `600342e2f3c5` built it,
empty, because the data to put back does not exist.

Revision ID: a3f81c60b204
Revises: 0057489a3ed5
Create Date: 2026-08-23 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "a3f81c60b204"
down_revision: Union[str, None] = "0057489a3ed5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table("user")


def downgrade() -> None:
    # Exactly what `600342e2f3c5` created, so that downgrading to any revision
    # before this one leaves the schema it expects rather than an approximation.
    op.create_table(
        "user",
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(length=100), nullable=False),
        sa.Column("email", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
