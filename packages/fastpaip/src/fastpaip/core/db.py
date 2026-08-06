"""The database engine and the unit of work built on it.

One engine per process, created lazily from :mod:`fastpaip.core.settings` and
cached, because a second engine means a second connection pool competing for the
same database.

Not built:
    Migrations. ``create_all`` creates tables that do not exist and does nothing
    to ones that do — so it is correct exactly once per database and silently
    insufficient every time a column changes afterwards. Alembic is what belongs
    here, and until it exists this is a development convenience that must not be
    what production relies on.

    An async engine. Sessions here are synchronous, so every query blocks its
    thread. See ``SqlSessionRepository`` for what that costs and when it starts
    mattering.
"""

from collections.abc import AsyncIterator
from functools import lru_cache

from sqlmodel import Session, SQLModel, create_engine

from fastpaip.core.settings import get_settings


@lru_cache
def get_engine():
    """Return the process-wide engine, created once."""
    return create_engine(get_settings().database_url)


def create_tables() -> None:
    """Create any table that does not exist yet. See the migrations gap above."""
    # Imported for the side effect of registering tables on SQLModel.metadata.
    # Without this, create_all sees an empty registry and silently creates
    # nothing — the failure then appears much later, as a missing table.
    from fastpaip.chat import models as _chat_models  # noqa: F401
    from fastpaip.ingestion import models as _ingestion_models  # noqa: F401

    SQLModel.metadata.create_all(get_engine())


async def session_scope() -> AsyncIterator[Session]:
    """Yield a session for one request, and close it afterwards.

    Deliberately does not commit. Committing here would make every request a
    single implicit transaction regardless of what it did, and hide from each
    caller the question of when its work is durable.

    ``async`` despite everything inside being synchronous, and that is the whole
    point. FastAPI runs a *synchronous* dependency in a worker thread, so the
    session would be opened on one thread and then used by an ``async`` endpoint
    on the event loop thread. A SQLAlchemy ``Session`` is not thread-safe. SQLite
    refuses outright — "SQLite objects created in a thread can only be used in
    that same thread" — and other drivers do something worse, which is to
    proceed. Declaring this ``async`` keeps creation and use on one thread.

    The cost is the one already noted above: the queries block the event loop.
    That trade is deliberate — blocking is a latency problem with a known fix,
    while sharing a session across threads is a correctness problem that shows
    up as corruption under load.
    """
    with Session(get_engine()) as session:
        yield session
