"""The migrations and the models must describe the same schema.

Two things build a database here. Deployments replay Alembic migrations; tests
call `create_tables`, which goes straight from the models. Nothing forces those
to agree, and when they disagree the symptom is the worst kind: every test
passes, because tests use the models — and production is missing a column.

The usual way in is ordinary. Someone adds a field, runs the tests, sees green,
and ships without generating a migration. This test is what makes that fail
where it is cheap to fix.
"""

import pathlib

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine
from sqlmodel import SQLModel

# Imported for the side effect of registering every table on SQLModel.metadata,
# which is the thing being compared against.
from fastpaip.auth import models as _auth_models  # noqa: F401
from fastpaip.chat import models as _chat_models  # noqa: F401
from fastpaip.core.settings import get_settings
from fastpaip.ingestion import models as _ingestion_models  # noqa: F401

ALEMBIC_INI = pathlib.Path(__file__).parent.parent / "alembic.ini"


@pytest.fixture(name="migrated_db")
def _migrated_db(tmp_path, monkeypatch):
    """A database built by replaying every migration."""
    database = tmp_path / "migrated.db"
    monkeypatch.setenv("FASTPAIP_DATABASE_URL", f"sqlite+aiosqlite:///{database}")
    # env.py reads the URL through get_settings, which is cached for the process.
    get_settings.cache_clear()

    command.upgrade(Config(str(ALEMBIC_INI)), "head")

    get_settings.cache_clear()
    return database


def test_migrations_produce_exactly_what_the_models_describe(migrated_db):
    """No pending autogenerate diff against a fully migrated database.

    Fails when a model changed without a migration, and equally when a migration
    was hand-edited into saying something the models do not.
    """
    # A synchronous engine purely to inspect: alembic's comparison API is
    # synchronous, and this connection reads schema rather than serving traffic.
    engine = create_engine(f"sqlite:///{migrated_db}")
    with engine.connect() as connection:
        context = MigrationContext.configure(connection, opts={"compare_type": True})
        differences = compare_metadata(context, SQLModel.metadata)

    assert differences == [], (
        "migrations and models disagree; run:\n"
        "  just makemigration -m 'describe the change'\n"
        f"differences: {differences}"
    )


def test_every_model_table_exists_after_migrating(migrated_db):
    """A cheaper check with a much clearer failure than a metadata diff.

    When something is simply missing, this names the table.
    """
    engine = create_engine(f"sqlite:///{migrated_db}")
    with engine.connect() as connection:
        from sqlalchemy import inspect

        present = set(inspect(connection).get_table_names())

    expected = set(SQLModel.metadata.tables)
    assert expected <= present, f"missing after migration: {sorted(expected - present)}"
