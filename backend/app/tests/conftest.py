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
import os
import sys
import uuid

import pytest
import sqlalchemy
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool
from sqlmodel import Session, SQLModel

# Imported for the side effect of registering every table on SQLModel.metadata,
# which is what both the schema build and the truncation below iterate over.
from bacteria.app import models as _root_models  # noqa: F401
from bacteria.app.auth import models as _auth_models  # noqa: F401
from bacteria.app.chat import models as _chat_models  # noqa: F401
from bacteria.app.core import observability
from bacteria.app.core import settings as settings_module
from bacteria.app.core.settings import ENV_PREFIX, Settings, get_settings
from bacteria.app.ingestion import models as _ingestion_models  # noqa: F401

LOOP_FACTORY = asyncio.SelectorEventLoop if sys.platform == "win32" else None
"""The loop class the tests run on, or ``None`` to accept the default.

Mirrors `bacteria.app.core.platform.event_loop_factory`, and is separate from it
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
    factory, not a policy. `bacteria.app.core.platform` explains why the policy
    route is a dead end there, and the hook here is pytest-asyncio's equivalent
    of the ``loop_factory`` argument that beat it.

    Must return a mapping rather than ``None``: pytest-asyncio treats a
    registered hook that answers ``None`` as a configuration error, so the
    non-Windows branch names the default explicitly.
    """
    return {"loop": LOOP_FACTORY or asyncio.new_event_loop}


KEPT_FROM_THE_AMBIENT_ENVIRONMENT = frozenset({f"{ENV_PREFIX}DATABASE_URL"})
"""The only ``BACTERIA_*`` variable a test run inherits from outside.

Kept because the suite genuinely reads it: :func:`database_url` derives the
throwaway database's name from whatever this deployment is configured with, so
pointing a run at a different Postgres has to keep working.
"""


@pytest.fixture(scope="session", autouse=True)
def _ignore_ambient_configuration():
    """Start the run without the developer's own ``BACTERIA_*`` settings.

    The Justfile's first line is ``set dotenv-load``, so ``just test-app`` hands
    pytest the contents of `.env` before Python starts. That is right for
    ``just serve`` and wrong for a test suite: a developer who configures the
    project — ``BACTERIA_MODEL_PROVIDER=gemini``, extraction enabled — then runs
    the supported command and watches fifteen tests fail on settings they never
    set and jobs they never queued.

    It also fails asymmetrically, which is the worst part. `.env` is gitignored,
    so CI has none and stays green; the suite breaks only for people who have
    configured the project, and passes for the machine that has not. A gate that
    cannot fail where it is enforced is a gate that teaches people to distrust it
    locally.

    Session-scoped and before everything, so :func:`database_url` and the rest
    build on a known environment rather than on whatever happened to be exported.
    A test that wants one of these settings sets it itself, which is also what
    makes the dependency visible at the point it matters.
    """
    patch = pytest.MonkeyPatch()

    # Three doors, and closing two is not enough -- which is what made this
    # confusing to diagnose, twice. `just` exports `.env` into the recipe's
    # environment; `Settings` *separately* reads the same file into its own
    # fields, relative to the working directory. So a run from the repository
    # root was configured twice over, and a run from `backend/app` -- where there
    # is no `.env` -- was configured not at all, which is why the suite looked
    # green from one directory and failed from another.
    patch.setitem(Settings.model_config, "env_file", None)

    # The third door, and it reopens the first two. `load_env_file` calls
    # `load_dotenv` on its own, so it writes `.env` into `os.environ` at the
    # moment an entrypoint runs -- which the ASGI lifespan does, and which the
    # tests drive on purpose. Deleting a variable below is therefore not enough
    # to keep it deleted: `test_no_worker_runs_in_the_api_by_default` did
    # `delenv("BACTERIA_RUN_WORKER_IN_API")`, started the lifespan, and got the
    # value straight back from the file -- so a test asserting the *safe default*
    # asserted it against a machine where the developer had turned the worker on.
    # It failed only for people who had configured the project, and passed in CI,
    # where there is no `.env` at all.
    #
    # Pointed at a name that cannot exist rather than patching `load_env_file`
    # out: the entrypoint really does call it, and the honest statement is that
    # this run has no dotenv file, not that loading one does nothing.
    patch.setattr(settings_module, "ENV_FILE", ".env.absent-under-test")

    for name in list(os.environ):
        if (
            name.upper().startswith(ENV_PREFIX)
            and name.upper() not in KEPT_FROM_THE_AMBIENT_ENVIRONMENT
        ):
            patch.delenv(name, raising=False)

    yield
    patch.undo()


@pytest.fixture(scope="session", autouse=True)
def _no_observability_in_tests():
    """The suite does not acquire an exporter, and ADR 0003 says so in as many words.

    Instrumentation is installed by entrypoints, and the ASGI lifespan is an
    entrypoint the tests drive on purpose — so without this every ``TestClient``
    configures Logfire, patches the psycopg driver and the provider SDK, and
    instruments a fresh FastAPI application. Nothing is exported, because no
    token is set. What it does produce is console spans in the middle of test
    output and OpenTelemetry's "attempting to instrument while already
    instrumented" warning once per application built, which is once per test.

    Patched here rather than guarded in the module, because "am I under test" is
    not a question production code should be able to ask. The suite is the thing
    that knows, so the suite is what says so.
    """
    patch = pytest.MonkeyPatch()
    patch.setattr(observability, "configure", lambda service_name: None)
    patch.setattr(observability, "instrument_app", lambda app: None)
    yield
    patch.undo()


@pytest.fixture(autouse=True)
def _restore_environment():
    """Undo whatever a test did to ``os.environ``, for every test.

    One test's environment must not reach the next one, and the path from A to B
    is shorter than it looks. ``load_env_file`` writes a developer's real `.env`
    into the process environment, and it is *correct* for it to do that — the
    provider SDKs read unprefixed names from there and nothing else puts them in.
    Any test that starts the ASGI lifespan therefore loads it, legitimately, and
    every test after that inherits the result.

    That was not hypothetical. A `.env` carrying ``BACTERIA_MODEL_PROVIDER`` and
    ``BACTERIA_MEMORY_EXTRACTION_ENABLED`` made fifteen tests fail: settings
    tests read a provider they never set, and chat tests inherited an extraction
    flag and tried to enqueue with no queue open. None of the failures were about
    the code under test, and none of them happened in CI, where `.env` does not
    exist — so the suite failed for exactly the people who had configured the
    project and passed for the machine that had not.

    A snapshot rather than a list of variables to unset, because the next
    variable to leak is by definition one nobody has thought of. Restoring in
    place rather than rebinding ``os.environ``: it is a special mapping that
    writes through to the real process environment, and replacing the object
    would leave that untouched.
    """
    saved = dict(os.environ)
    yield
    os.environ.clear()
    os.environ.update(saved)


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
    name = f"bacteria_test_{uuid.uuid4().hex[:12]}"

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
    patch.setenv("BACTERIA_DATABASE_URL", url)

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
    # get_settings is cached, and tests monkeypatch BACTERIA_* variables. Clear
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
