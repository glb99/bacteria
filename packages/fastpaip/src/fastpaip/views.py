"""Assembles the ASGI application from its features.

A factory rather than a module-level ``app``, so that a test can build an
instance with its own dependency overrides instead of mutating a global one that
every other test shares.
"""

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI

from fastpaip.chat.views import router as chat_router
from fastpaip.ingestion.views import router as ingestion_router


def lifespan_running(setup: Callable[[], Awaitable[None]]):
    """Wrap a coroutine as a lifespan that runs it at startup.

    Startup work belongs here rather than at module import, for three reasons
    of decreasing certainty.

    Importing a module must not touch a database. At import, ``create_tables()``
    would connect to whatever ``FASTPAIP_DATABASE_URL`` names, so collecting
    tests on a machine without one fails at import, and any tool that imports
    the app merely to read its routes has to have a database first.

    ``anyio.run()`` at import would spin up and tear down a whole event loop as
    a side effect of an import statement.

    And a driver-dependent one: an ``asyncpg`` connection is bound to the loop
    that created it, so a pool filled by a throwaway import-time loop is holding
    connections to a loop that is gone by the first request. ``aiosqlite``
    tolerates this, so it is not currently observable — but Postgres is the
    target, and it will be.

    Taking the work as an argument keeps the decision — whether this deployment
    builds its own schema — in the entrypoint, where deployment decisions live.
    Once migrations exist, no deployment does, and this disappears.
    """

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        await setup()
        yield

    return lifespan


def create_app(lifespan=None) -> FastAPI:
    """Build the application. Adding a feature means adding a router here.

    Args:
        lifespan: Startup and shutdown behaviour, supplied by the entrypoint.
            ``None`` means the application assumes its schema already exists —
            which is what a deployment with real migrations would want, and what
            a test that built its own tables already has.
    """
    app = FastAPI(title="fastpaip", lifespan=lifespan)
    app.include_router(chat_router)
    app.include_router(ingestion_router)

    @app.get("/health", tags=["ops"])
    async def health() -> dict[str, str]:
        """Liveness only: the process is up and serving.

        Deliberately does not touch the database. A health check that fails when
        a dependency is down causes the orchestrator to restart a process that
        was working, which turns one outage into two.
        """
        return {"status": "ok"}

    return app
