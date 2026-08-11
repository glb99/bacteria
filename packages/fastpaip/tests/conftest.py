"""Shared database fixtures, pointed at the database this application deploys on.

Every test here used to build its own in-memory SQLite engine — six copies of
the same four lines, none of them exercising Postgres. That was not free. SQLite
ignores ``DateTime(timezone=True)`` and hands back a naive datetime, so
``_tz_column()`` in the models — used by batches, transcripts, and
``ApiKey.revoked_at`` — round-tripped one way under test and another in
production. Any comparison against an aware ``datetime.now(timezone.utc)`` raises
``TypeError`` on exactly one of them, and it was not the one being tested.

The shape here is one throwaway database per run, created from the models, with
every table truncated between tests. Truncation rather than a database per test
because creating one costs a few hundred milliseconds and there are forty-odd
tests; ``RESTART IDENTITY`` is part of it so that a test may still assume it is
the first writer and get id 1.

The schema is built from the models rather than by replaying migrations.
Faithfulness to the deployed schema is `test_migrations.py`'s job, and it does
that properly — replaying the whole history onto an empty database and diffing
the result. Doing it again here would cost every run the same time to assert the
same thing.
"""

import asyncio
import sys
import uuid

import pytest
import sqlalchemy

# Imported for the side effect of registering every table on SQLModel.metadata,
# which is what both the schema build and the truncation below iterate over.
from fastpaip import models as _root_models  # noqa: F401
from fastpaip.auth import models as _auth_models  # noqa: F401
from fastpaip.chat import models as _chat_models  # noqa: F401
from fastpaip.core.settings import get_settings
from fastpaip.ingestion import models as _ingestion_models  # noqa: F401
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool
from sqlmodel import Session, SQLModel

LOOP_FACTORY = asyncio.SelectorEventLoop if sys.platform == "win32" else None
"""The loop class the tests run on, or ``None`` to accept the default.

Mirrors `fastpaip.core.platform.event_loop_factory`, and is separate from it
because that one is about the loop a *process* runs on and this one is about the
loop a test runs on.
"""


def pytest_asyncio_loop_factories(config, item):
    """Give pytest-asyncio a loop psycopg can actually use.

    Windows defaults to ``ProactorEventLoop``, and psycopg's async mode refuses
    to run on it — every connection raises ``InterfaceError`` before a query is
    sent. Under SQLite this never came up, which is part of why the backend
    split was able to persist.

    The same loop choice the application makes, by the same mechanism: a
    factory, not a policy. `fastpaip.core.platform` explains why the policy
    route is a dead end there, and the hook here is pytest-asyncio's equivalent
    of the ``loop_factory`` argument that beat it.

    Must return a mapping rather than ``None``: pytest-asyncio treats a
    registered hook that answers ``None`` as a configuration error, so the
    non-Windows branch names the default explicitly.
    """
    return {"loop": LOOP_FACTORY or asyncio.new_event_loop}


@pytest.fixture(scope="session", name="backend_options")
def _backend_options() -> dict:
    """Passed to every `TestClient`, which has to be told separately.

    `TestClient` runs the application on its own loop in its own thread, opened
    by anyio rather than by pytest-asyncio, so the hook above does not reach it.
    Left unset, that loop is a ``ProactorEventLoop`` on Windows and every query
    the application makes fails — while the test's own fixtures, on
    pytest-asyncio's loop, keep working. The resulting error names psycopg and
    looks nothing like a missing argument here, which is why this is a fixture
    every HTTP test requests rather than a default someone has to remember.
    """
    return {"loop_factory": LOOP_FACTORY} if LOOP_FACTORY else {}


@pytest.fixture(scope="session")
def database_url() -> str:
    """A throwaway Postgres database, dropped when the run ends.

    Named with a uuid so two runs — or a run and an interrupted one — never
    share state. Skips rather than fails when Postgres is unreachable, loudly
    enough to be actionable, because the alternative is a suite nobody can run
    without Docker started.
    """
    configured = get_settings().database_url
    # get_settings is cached for the process, and this is the first call in the
    # run. Cleared so the patched URL below is what everything after here sees.
    get_settings.cache_clear()

    stem, _, _ = configured.rpartition("/")
    name = f"fastpaip_test_{uuid.uuid4().hex[:12]}"

    # connect_timeout because the default is no timeout: with nothing listening
    # on 5432 this blocks for minutes instead of being refused, and a suite that
    # hangs when Postgres is down is worse than one that fails.
    admin = create_engine(
        f"{stem}/postgres",
        isolation_level="AUTOCOMMIT",
        connect_args={"connect_timeout": 3},
    )
    try:
        with admin.connect() as connection:
            connection.execute(text(f'CREATE DATABASE "{name}"'))
    except sqlalchemy.exc.OperationalError:
        admin.dispose()
        pytest.skip("Postgres unreachable; run `just db-up`")

    url = f"{stem}/{name}"
    patch = pytest.MonkeyPatch()
    patch.setenv("FASTPAIP_DATABASE_URL", url)

    # The schema is built synchronously, before any event loop exists, so that
    # this fixture stays usable by both the async and the sync tests below.
    schema_engine = create_engine(url)
    SQLModel.metadata.create_all(schema_engine)
    schema_engine.dispose()

    try:
        yield url
    finally:
        patch.undo()
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


def _truncate(url: str) -> None:
    """Empty every table the application owns, and reset its sequences.

    Synchronous and on its own connection, deliberately: this runs between
    tests, where there may be no event loop, and it must not depend on the
    engine under test having been disposed cleanly.

    ``CASCADE`` because the tables are related by foreign key and truncating
    them one at a time in dependency order is a list that would need updating
    every time a model is added.
    """
    tables = ", ".join(f'"{name}"' for name in SQLModel.metadata.tables)
    if not tables:
        return
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    engine.dispose()


@pytest.fixture(name="engine")
async def _engine(database_url):
    """An async engine on the test database, with a clean schema.

    Truncation happens *before* the test rather than after, so a test that
    crashes hard leaves the next one unaffected — cleanup that only runs on the
    happy path is cleanup that fails when it matters.

    A fresh engine per test rather than a shared one, and ``NullPool`` on top of
    that. Both are about the same hazard: a pooled connection belongs to the
    loop that opened it, and an HTTP test drives *two* loops — pytest-asyncio's,
    where the fixtures run, and the one `TestClient` opens in its own thread,
    where the application runs. A pool spanning those hands the same psycopg
    connection to both, and the symptom is ``another command is already in
    progress`` from whichever got there second.

    SQLite hid this too. `StaticPool` with ``check_same_thread=False`` is
    explicitly a shared single connection, and aiosqlite serializes onto its own
    worker thread, so the overlap was harmless there and fatal here.
    """
    _truncate(database_url)
    # get_settings is cached, and tests monkeypatch FASTPAIP_* variables. Clear
    # it here so each test builds settings from its own environment rather than
    # inheriting whatever the first test in the run happened to set.
    get_settings.cache_clear()

    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        yield engine
    finally:
        await engine.dispose()
        get_settings.cache_clear()


@pytest.fixture(name="sync_session")
def _sync_session(database_url):
    """A synchronous session, for the repositories that are still synchronous."""
    _truncate(database_url)
    engine = create_engine(database_url)
    with Session(engine) as session:
        yield session
    engine.dispose()
