"""widen document entity label

Revision ID: c4e8b1a07d22
Revises: b7c1a9e4d2f0
Create Date: 2026-10-20 13:20:00.000000

"""
import sqlalchemy as sa

from alembic import op

revision = "c4e8b1a07d22"
down_revision = "b7c1a9e4d2f0"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        "document_entity",
        "label",
        existing_type=sa.String(length=1024),
        type_=sa.Text(),
        existing_nullable=False,
    )


def downgrade():
    op.alter_column(
        "document_entity",
        "label",
        existing_type=sa.Text(),
        type_=sa.String(length=1024),
        existing_nullable=False,
    )
