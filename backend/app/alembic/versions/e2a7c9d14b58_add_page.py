"""add page

Revision ID: e2a7c9d14b58
Revises: c4e8b1a07d22
Create Date: 2026-10-21 12:00:00.000000

"""
import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "e2a7c9d14b58"
down_revision = "c4e8b1a07d22"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "page",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("page_index", sa.Integer(), nullable=False),
        sa.Column(
            "image_path",
            sqlmodel.sql.sqltypes.AutoString(length=1024),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["document_id"], ["document.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "document_id",
            "page_index",
            name="uq_page_document_id_page_index",
        ),
    )


def downgrade():
    op.drop_table("page")
