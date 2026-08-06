"""The database engine and the unit of work built on it.

Async throughout, because a query is I/O and this application's rule is that I/O
is awaited. That rule was followed at the signature level and broken underneath
for a while — the repositories were ``async def`` around synchronous SQLModel
calls, which is async's shape without async's benefit.

One engine per process, created lazily from :mod:`fastpaip.core.settings` and
cached, because a second engine means a second connection pool competing for the
same database.

A note on what "async" buys per backend, since it is not the same everywhere.
SQLite has no async C API, so ``aiosqlite`` runs the same blocking calls on a
worker thread and awaits the result — the blocking is moved off the event loop
rather than eliminated. ``asyncpg`` is genuinely non-blocking, a real async
socket protocol with no thread involved. The development default is SQLite,
where the win is modest; the production target is Postgres, where it is the
difference between serializing every request behind a network round trip and
not.

Schema is owned by Alembic, in ``packages/fastpaip/migrations``. Nothing here
creates tables at startup: a deployment runs ``alembic upgrade head`` before the
application starts, so the schema a running process sees is one someone wrote
down and reviewed. ``create_tables`` below exists for tests, which want a schema
in one call and do not want to replay a migration history to get it — and a test
asserts the two agree, since a schema built two ways is a schema that can drift.
"""

from collections.abc import AsyncIterator
from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from fastpaip.core.settings import get_settings


@lru_cache
def get_engine() -> AsyncEngine:
    """Return the process-wide engine, created once.

    Cached, so one pool serves the process.

    How well a pooled connection survives the event loop changing underneath it
    depends on the driver, and the difference is worth knowing before assuming
    either way. ``aiosqlite`` tolerates it — each connection owns a worker
    thread and awaits on whatever loop is currently running — and this was
    checked rather than assumed. ``asyncpg`` does not: its connections are
    documented as bound to the loop that created them. Since Postgres is the
    production target, treat the engine as loop-bound even though the
    development driver forgives it.
    """
    return create_async_engine(get_settings().database_url)


async def create_tables(engine: AsyncEngine | None = None) -> None:
    """Build the whole schema in one call, from the models.

    For tests. A deployment runs ``alembic upgrade head`` instead — this skips
    the migration history entirely, so it can produce a schema that no sequence
    of migrations would, which is exactly the drift
    ``test_migrations.py`` exists to catch.

    Args:
        engine: Defaults to the process engine. Tests pass their own, which is
            the only reason this takes an argument.
    """
    # Imported for the side effect of registering tables on SQLModel.metadata.
    # Without this, create_all sees an empty registry and silently creates
    # nothing — the failure then appears much later, as a missing table.
    from fastpaip import models as _root_models  # noqa: F401
    from fastpaip.auth import models as _auth_models  # noqa: F401
    from fastpaip.chat import models as _chat_models  # noqa: F401
    from fastpaip.ingestion import models as _ingestion_models  # noqa: F401

    async with (engine or get_engine()).begin() as connection:
        # create_all is a synchronous SQLAlchemy API; run_sync drives it on the
        # async connection rather than opening a second, synchronous one.
        await connection.run_sync(SQLModel.metadata.create_all)


async def session_scope() -> AsyncIterator[AsyncSession]:
    """Yield a session for one request, and close it afterwards.

    Deliberately does not commit. Committing here would make every request a
    single implicit transaction regardless of what it did, and hide from each
    caller the question of when its work is durable.
    """
    async with AsyncSession(get_engine()) as session:
        yield session
