"""The database engine and the unit of work built on it.

Async throughout, because a query is I/O and this application's rule is that I/O
is awaited. That rule was followed at the signature level and broken underneath
for a while — the repositories were ``async def`` around synchronous SQLModel
calls, which is async's shape without async's benefit.

One engine per process, created lazily from :mod:`fastpaip.core.settings` and
cached, because a second engine means a second connection pool competing for the
same database.

Postgres everywhere — development, tests, and deployment — via psycopg 3. There
is no SQLite fallback, and the absence is deliberate: the one that existed for
development hid a real difference. SQLite ignores ``DateTime(timezone=True)``
and returns naive datetimes, so every timestamp in this application round-tripped
one way under test and another in production, and no test could see it.

Schema is owned by Alembic, in ``packages/fastpaip/migrations``. Nothing here
creates tables, at startup or otherwise: a deployment runs ``alembic upgrade
head`` before the application starts, so the schema a running process sees is one
someone wrote down and reviewed. Tests build theirs from the models in
``conftest.py``, and ``test_migrations.py`` asserts the two agree — a schema
built two ways is a schema that can drift.
"""

from collections.abc import AsyncIterator
from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession

from fastpaip.core.settings import get_settings


@lru_cache
def get_engine() -> AsyncEngine:
    """Return the process-wide engine, created once.

    Cached, so one pool serves the process.

    Treat the engine as bound to the loop that filled its pool. A psycopg
    connection handed to a second loop fails with ``another command is already
    in progress`` when the two overlap, which is a confusing way to learn it —
    the test suite hit exactly this once its fixtures and `TestClient` started
    sharing an engine across their two loops, and `tests/conftest.py` uses
    ``NullPool`` because of it.
    """
    return create_async_engine(get_settings().database_url)


def include_name(name: str | None, type_: str, parent_names: dict) -> bool:
    """Hide tables this application does not own from Alembic's autogenerate.

    Procrastinate's four tables are installed by a migration that runs its
    shipped SQL, so they exist in the database and in no SQLModel metadata.
    Without this filter, autogenerate sees tables it does not recognize and
    writes a migration to drop them — and the drift test reports a difference
    that is not one.

    Lives here rather than in ``migrations/env.py`` because that module calls
    into Alembic's context at import and cannot be imported by anything else,
    including the test that needs the same filter to compare like with like.
    """
    # Suppressed rather than rewritten as the negated one-liner ruff suggests:
    # this reads as a rule ("hide procrastinate's tables"), where
    # `return not (a and b and c)` reads as a puzzle. RUF100 will flag the
    # suppression below if the rule ever stops firing.
    if type_ == "table" and name is not None and name.startswith("procrastinate"):  # noqa: SIM103
        return False
    return True


async def session_scope() -> AsyncIterator[AsyncSession]:
    """Yield a session for one request, and close it afterwards.

    Deliberately does not commit. Committing here would make every request a
    single implicit transaction regardless of what it did, and hide from each
    caller the question of when its work is durable.
    """
    async with AsyncSession(get_engine()) as session:
        yield session
