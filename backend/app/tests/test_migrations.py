"""The migrations and the models must describe the same schema.

Two things build a database here. Deployments replay Alembic migrations; the
test suite goes straight from the models, in `conftest.py`. Nothing forces those
to agree, and when they disagree the symptom is the worst kind: every test
passes, because tests use the models — and production is missing a column.

The usual way in is ordinary. Someone adds a field, runs the tests, sees green,
and ships without generating a migration. This test is what makes that fail
where it is cheap to fix.

These run against real Postgres, not SQLite, and have to: one migration installs
procrastinate's schema from its own Postgres SQL, so replaying the history is
not something SQLite can do at all. Start it with `just db-up`.
"""

import pathlib
import uuid

import pytest
import sqlalchemy
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text
from sqlmodel import SQLModel

# Imported for the side effect of registering every table on SQLModel.metadata,
# which is the thing being compared against.
from bacteria.app import models as _root_models  # noqa: F401
from bacteria.app.auth import models as _auth_models  # noqa: F401
from bacteria.app.chat import models as _chat_models  # noqa: F401
from bacteria.app.core.db import include_name
from bacteria.app.core.settings import get_settings
from bacteria.app.graph import models as _graph_models  # noqa: F401
from bacteria.app.ingestion import models as _ingestion_models  # noqa: F401

ALEMBIC_INI = pathlib.Path(__file__).parent.parent / "alembic.ini"


def _sync_url(url: str) -> str:
    """No conversion needed, and saying so is the point.

    `postgresql+psycopg://` is psycopg 3's dialect and serves both modes:
    `create_engine` gives a synchronous engine, `create_async_engine` an async
    one. This function exists so the next person does not "fix" the apparent
    mismatch by stripping the prefix, which routes the URL to psycopg2.
    """
    return url


@pytest.fixture(name="migrated_db")
def _migrated_db(monkeypatch, require_postgres):
    """A throwaway database built by replaying every migration.

    A fresh database per run rather than a shared one, because a migration
    history is only meaningfully tested from empty — replaying it onto a
    database that already has the tables proves nothing.
    """
    settings_url = get_settings().database_url
    admin_url = _sync_url(settings_url.rsplit("/", 1)[0] + "/postgres")
    name = f"bacteria_migtest_{uuid.uuid4().hex[:12]}"

    # An explicit connect_timeout, because the default is no timeout at all:
    # with nothing listening on 5432 this blocks for minutes rather than being
    # refused, and a suite that hangs when Postgres is down is worse than one
    # that fails.
    admin = create_engine(
        admin_url, isolation_level="AUTOCOMMIT", connect_args={"connect_timeout": 3}
    )
    try:
        with admin.connect() as connection:
            connection.execute(text(f'CREATE DATABASE "{name}"'))
    except sqlalchemy.exc.OperationalError:
        require_postgres("Postgres unreachable; run `just db-up`")

    target = settings_url.rsplit("/", 1)[0] + "/" + name
    monkeypatch.setenv("BACTERIA_DATABASE_URL", target)
    # env.py reads the URL through get_settings, which is cached per process.
    get_settings.cache_clear()

    try:
        command.upgrade(Config(str(ALEMBIC_INI)), "head")
        yield _sync_url(target)
    finally:
        get_settings.cache_clear()
        with admin.connect() as connection:
            connection.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    f"WHERE datname = '{name}' AND pid <> pg_backend_pid()"
                )
            )
            connection.execute(text(f'DROP DATABASE IF EXISTS "{name}"'))
        admin.dispose()


def test_migrations_produce_exactly_what_the_models_describe(migrated_db):
    """No pending autogenerate diff against a fully migrated database.

    Fails when a model changed without a migration, and equally when a migration
    was hand-edited into saying something the models do not.
    """
    engine = create_engine(migrated_db)
    with engine.connect() as connection:
        context = MigrationContext.configure(
            connection,
            opts={"compare_type": True, "include_name": include_name},
        )
        differences = compare_metadata(context, SQLModel.metadata)
    engine.dispose()

    assert differences == [], (
        "migrations and models disagree; run:\n"
        '  just makemigration "describe the change"\n'
        f"differences: {differences}"
    )


def test_every_model_table_exists_after_migrating(migrated_db):
    """A cheaper check with a much clearer failure than a metadata diff.

    When something is simply missing, this names the table.
    """
    engine = create_engine(migrated_db)
    with engine.connect() as connection:
        present = set(inspect(connection).get_table_names())
    engine.dispose()

    expected = set(SQLModel.metadata.tables)
    assert expected <= present, f"missing after migration: {sorted(expected - present)}"


def test_the_job_schema_is_installed_by_the_migration_history(migrated_db):
    """Procrastinate's tables come from its SQL, not from a model.

    Nothing above would notice if that migration stopped running, because the
    metadata comparison is told to ignore these tables — so the absence would
    look exactly like agreement.
    """
    engine = create_engine(migrated_db)
    with engine.connect() as connection:
        present = set(inspect(connection).get_table_names())
    engine.dispose()

    assert {"procrastinate_jobs", "procrastinate_events"} <= present


def test_every_memory_table_carries_the_same_content_columns():
    """The three memory tables differ in their keys and in nothing else.

    They inherit `MemoryContent` so that a field is added once rather than
    three times. That only helps while it holds: the plausible mistake is
    adding a column to one class instead of the base, and the one most likely
    to be forgotten is `chat_user_memory_entry` — the table where an
    `expires_at` would matter most, since a user-scoped memory outlives every
    session it was written in.

    Compares content columns only. The keys are *supposed* to differ; that
    difference is what ADR 0021 and ADR 0017 are about.
    """
    from bacteria.app.chat.models import ChatMemoryEntry, ChatMemoryProposal, ChatUserMemoryEntry

    def content(model) -> set[str]:
        table = model.__table__
        keys = {column.name for column in table.primary_key.columns}
        return {column.name for column in table.columns} - keys

    session_scoped = content(ChatMemoryEntry)

    assert session_scoped, "discovery found no content columns, so this proves nothing"
    assert content(ChatUserMemoryEntry) == session_scoped
    # The proposal table's `source` is part of its key rather than content,
    # which is exactly the rule that keeps two proposers from overwriting one
    # another -- so it is expected to be absent here.
    assert content(ChatMemoryProposal) == session_scoped - {"source"}
