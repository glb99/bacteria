"""Assembles the ASGI application from its features.

A factory rather than a module-level ``app``, so that a test can build an
instance with its own dependency overrides instead of mutating a global one that
every other test shares.
"""

from fastapi import FastAPI

from bacteria.app.auth.views import router as auth_router
from bacteria.app.chat.views import router as chat_router
from bacteria.app.ingestion.views import router as ingestion_router


def create_app(lifespan=None) -> FastAPI:
    """Build the application. Adding a feature means adding a router here.

    Args:
        lifespan: Startup and shutdown behaviour, supplied by the entrypoint.
            ``None`` builds an application that assumes everything it needs is
            already running — the schema migrated, no job queue to open. That is
            what the tests want, and it is why the parameter exists rather than
            this module importing the real lifespan itself: composing a process
            is `entrypoints/`' job, not this one's.
    """
    app = FastAPI(title="bacteria", lifespan=lifespan)
    # First, and only because it reads that way in `/docs`: establishing a
    # session is the first thing a browser does, and the generated page lists
    # tags in the order routers are added.
    app.include_router(auth_router)
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
