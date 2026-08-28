"""graph rows carry an ontology and an author.

All three columns are nullable, and the nulls are the point: every row
written before this belongs to its owner's memory and was stated by nobody
this system recorded. A default would assert something about them that is
not true, which is the backfilling the log forbids.

Revision ID: 99da2a5e164f
Revises: a02f2941059b
Create Date: 2026-08-28 18:15:45.492051
"""

from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "99da2a5e164f"
down_revision: Union[str, None] = "a02f2941059b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "graph_assertion", sa.Column("ontology", sqlmodel.sql.sqltypes.AutoString(), nullable=True)
    )
    op.add_column(
        "graph_assertion", sa.Column("stated_by", sqlmodel.sql.sqltypes.AutoString(), nullable=True)
    )
    op.create_index(
        op.f("ix_graph_assertion_ontology"), "graph_assertion", ["ontology"], unique=False
    )
    op.add_column(
        "graph_node", sa.Column("ontology", sqlmodel.sql.sqltypes.AutoString(), nullable=True)
    )
    op.create_index(op.f("ix_graph_node_ontology"), "graph_node", ["ontology"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_graph_node_ontology"), table_name="graph_node")
    op.drop_column("graph_node", "ontology")
    op.drop_index(op.f("ix_graph_assertion_ontology"), table_name="graph_assertion")
    op.drop_column("graph_assertion", "stated_by")
    op.drop_column("graph_assertion", "ontology")
