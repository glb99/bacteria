"""Alembic environment: how migrations find the database and the models.

Two things here are deliberate and easy to get wrong when copying a template.

The database URL comes from :mod:`fastpaip.core.settings`, not from
``alembic.ini``. A URL in the ini file is a second place the database can be
named, and the failure that produces — migrating one database while the
application talks to another — is quiet and confusing.

The engine is async, because the application's is. Alembic's migration API is
synchronous, so ``run_sync`` drives it over an async connection rather than
opening a second, synchronous one with different pooling and a different URL
dialect.
"""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlalchemy import pool
from sqlmodel import SQLModel

from fastpaip.core.settings import get_settings

# Imported for the side effect of registering tables on SQLModel.metadata.
# Without every model module imported here, autogenerate sees a table it does
# not know about and cheerfully writes a migration to drop it.
from fastpaip import models as _root_models  # noqa: F401
from fastpaip.auth import models as _auth_models  # noqa: F401
from fastpaip.chat import models as _chat_models  # noqa: F401
from fastpaip.ingestion import models as _ingestion_models  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

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
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        # SQLite cannot ALTER most things; batch mode rebuilds the table
        # instead. Harmless on Postgres, and the alternative is migrations that
        # only run on one of the two backends this project uses.
        render_as_batch=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Run migrations against a live database."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
