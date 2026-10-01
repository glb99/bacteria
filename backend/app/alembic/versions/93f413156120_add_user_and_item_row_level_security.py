"""add user and item row level security

Revision ID: 93f413156120
Revises: fe56fa70289e
Create Date: 2026-10-01 12:41:58.434273

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision = '93f413156120'
down_revision = 'fe56fa70289e'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE item ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE item FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY item_owner_isolation ON item
            FOR ALL
            USING (
                current_setting('app.current_user_id', true) IS NULL
                OR owner_id = current_setting('app.current_user_id', true)::uuid
            )
            WITH CHECK (
                current_setting('app.current_user_id', true) IS NULL
                OR owner_id = current_setting('app.current_user_id', true)::uuid
            )
        """
    )
    op.execute('ALTER TABLE "user" ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE "user" FORCE ROW LEVEL SECURITY')
    op.execute(
        """
        CREATE POLICY user_self_isolation ON "user"
            FOR ALL
            USING (
                current_setting('app.current_user_id', true) IS NULL
                OR id = current_setting('app.current_user_id', true)::uuid
            )
            WITH CHECK (
                current_setting('app.current_user_id', true) IS NULL
                OR id = current_setting('app.current_user_id', true)::uuid
            )
        """
    )


def downgrade():
    op.execute('DROP POLICY IF EXISTS user_self_isolation ON "user"')
    op.execute('ALTER TABLE "user" NO FORCE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE "user" DISABLE ROW LEVEL SECURITY')
    op.execute("DROP POLICY IF EXISTS item_owner_isolation ON item")
    op.execute("ALTER TABLE item NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE item DISABLE ROW LEVEL SECURITY")
