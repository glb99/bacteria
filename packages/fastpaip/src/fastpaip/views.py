"""Assembles the ASGI application from its features.

A factory rather than a module-level ``app``, so that a test can build an
instance with its own dependency overrides instead of mutating a global one that
every other test shares.
"""

from fastapi import FastAPI

from fastpaip.chat.views import router as chat_router


def create_app() -> FastAPI:
    """Build the application. Adding a feature means adding a router here."""
    app = FastAPI(title="fastpaip")
    app.include_router(chat_router)

    @app.get("/health", tags=["ops"])
    async def health() -> dict[str, str]:
        """Liveness only: the process is up and serving.

        Deliberately does not touch the database. A health check that fails when
        a dependency is down causes the orchestrator to restart a process that
        was working, which turns one outage into two.
        """
        return {"status": "ok"}

    return app
