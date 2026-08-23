"""Alembic environment: how migrations find the database and the models.

Three things here are deliberate and easy to get wrong when copying a template.

The database URL comes from :mod:`bacteria.app.core.settings`, not from
``alembic.ini``. A URL in the ini file is a second place the database can be
named, and the failure that produces — migrating one database while the
application talks to another — is quiet and confusing.

The engine here is **synchronous**, unlike the application's. Alembic's
migration API is synchronous, so an async engine bought nothing but a
``run_sync`` wrapper — and on Windows it bought an outright failure, because
psycopg's async mode cannot run on the default event loop. Migrations are a
short-lived administrative task with no concurrency to gain from, so the driver
prefix is stripped and a normal engine is used.

``include_name`` comes from :mod:`bacteria.app.core.db` rather than being defined
here, because this module calls into Alembic's context at import and so cannot
be imported by anything else — including the drift test, which needs the same
filter to compare like with like.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlmodel import SQLModel

# Imported for the side effect of registering tables on SQLModel.metadata.
# Without every model module imported here, autogenerate sees a table it does
# not know about and cheerfully writes a migration to drop it.
from bacteria.app.auth import models as _auth_models  # noqa: F401
from bacteria.app.chat import models as _chat_models  # noqa: F401
from bacteria.app.core.db import include_name
from bacteria.app.core.settings import get_settings
from bacteria.app.ingestion import models as _ingestion_models  # noqa: F401

config = context.config

if config.config_file_name is not None:
    # `disable_existing_loggers=False`, and it is not a preference. `fileConfig`
    # defaults it to True, which switches off every logger that already exists
    # rather than merely reconfiguring the ones named in `alembic.ini` -- so
    # every `bacteria.*` logger created before this import goes permanently
    # silent, having logged nothing wrong and reported nothing about it.
    #
    # Alembic's generated template ships the defaulted call and it is harmless
    # there, because `alembic` is its own process. Here `migrations/env.py` is
    # imported by the drift test inside the pytest process, so the damage
    # outlives the migration: any later test asserting on a log record sees an
    # empty capture, and whether it does depends on test *ordering*. That is how
    # this was found -- a settings test passing alone and failing in the suite.
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# The URL is used as-is. `postgresql+psycopg://` is psycopg 3's dialect and it
# serves both modes: `create_engine` gives a synchronous engine from it,
# `create_async_engine` an async one. Stripping the prefix to "make it sync"
# hands the URL to psycopg2 instead, which is not installed.
config.set_main_option("sqlalchemy.url", get_settings().database_url)

target_metadata = SQLModel.metadata


def run_migrations_offline() -> None:
    """Emit SQL to stdout instead of running it.

    For environments where the person applying a change is not the person
    writing it, and the SQL has to be reviewed first.
    """
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_name=include_name,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live database."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        do_run_migrations(connection)
    connectable.dispose()


def do_run_migrations(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        include_name=include_name,
    )
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
