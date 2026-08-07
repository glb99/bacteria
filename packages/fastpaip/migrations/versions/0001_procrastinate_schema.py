"""install the procrastinate job schema

Procrastinate owns four tables of its own — jobs, events, workers, and periodic
defers — plus functions and triggers. It ships them as SQL rather than as
SQLAlchemy models, so autogenerate cannot see them and would happily write a
migration to drop them if they were applied out of band.

Applying them through Alembic instead means one migration history, one command
to bring a database up, and no second schema story to remember. The cost is
that upgrading procrastinate is not automatic: it publishes its own numbered
migration files, and a version bump needs a new Alembic revision running the
relevant one. Check its changelog before upgrading.

Revision ID: 0001_procrastinate
Revises: 600342e2f3c5
Create Date: 2026-08-07
"""

from typing import Sequence, Union

from alembic import op
from procrastinate.schema import SchemaManager

revision: str = "0001_procrastinate"
down_revision: Union[str, None] = "600342e2f3c5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Read at migration time rather than pasted in, so this revision installs
    # exactly the schema the pinned procrastinate expects. A copy would drift
    # from the library silently, and the symptom would be a worker failing on a
    # column it was written to use.
    op.execute(SchemaManager(connector=None).get_schema())


def downgrade() -> None:
    op.execute(
        """
        DROP TABLE IF EXISTS procrastinate_events CASCADE;
        DROP TABLE IF EXISTS procrastinate_periodic_defers CASCADE;
        DROP TABLE IF EXISTS procrastinate_jobs CASCADE;
        DROP TABLE IF EXISTS procrastinate_workers CASCADE;
        DROP TYPE IF EXISTS procrastinate_job_status CASCADE;
        DROP TYPE IF EXISTS procrastinate_job_event_type CASCADE;
        """
    )
