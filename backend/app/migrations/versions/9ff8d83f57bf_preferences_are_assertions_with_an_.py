"""preferences are assertions with an origin and a scope

Revision ID: 9ff8d83f57bf
Revises: 3f2d99665f81
Create Date: 2026-08-25 20:22:27.392492
"""

from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "9ff8d83f57bf"
down_revision: Union[str, None] = "3f2d99665f81"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # `server_default` rather than the bare NOT NULL autogenerate proposed, which
    # cannot apply to a table that already has rows. The values are not a
    # placeholder: every existing assertion came from the extractor and applies
    # everywhere, so `inferred` and `user` are what those rows have always meant.
    # Backfilling them states that rather than inventing it.
    #
    # The defaults stay on the columns afterwards. The application always supplies
    # both, so they are never reached in normal use -- they are there for the
    # `psql` insert during an incident, where a NOT NULL column with no default is
    # a footgun and a wrong-looking `inferred` is recoverable.
    op.add_column(
        "graph_assertion",
        sa.Column(
            "origin", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default="inferred"
        ),
    )
    op.add_column(
        "graph_assertion",
        sa.Column(
            "scope", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default="user"
        ),
    )
    op.create_index(op.f("ix_graph_assertion_origin"), "graph_assertion", ["origin"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_graph_assertion_origin"), table_name="graph_assertion")
    op.drop_column("graph_assertion", "scope")
    op.drop_column("graph_assertion", "origin")
