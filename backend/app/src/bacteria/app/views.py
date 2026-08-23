"""Assembles the ASGI application from its features.

A factory rather than a module-level ``app``, so that a test can build an
instance with its own dependency overrides instead of mutating a global one that
every other test shares.

**This module reads no settings, and that is load-bearing rather than tidy.**
`entrypoints/asgi.py` calls :func:`create_app` at module scope, because
production imports its ``app`` rather than calling ``main``. ``get_settings`` is
cached for the process, so a settings read from here would freeze configuration
at import time — the trap `core/settings.py` describes, which has already cost
this project a test suite that called a live model API. Anything this function
needs that a deployment could vary arrives as an argument.
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from bacteria.app.auth.views import router as auth_router
from bacteria.app.chat.views import router as chat_router
from bacteria.app.graph.views import router as graph_router
from bacteria.app.ingestion.views import router as ingestion_router

CONSOLE_DIR = Path(__file__).parent / "console"
"""Where a built console lives: inside the package, not beside the repository.

Package data rather than a configured path, and the alternatives are worse in
ways worth recording. A setting cannot be read here at all — see the module
docstring. A path relative to the working directory resolves differently for
`just serve` at the repository root than for a container started somewhere else,
which is the same two-mechanisms-that-agree-until-they-do-not failure
`load_env_file` documents. Being installed with the distribution means the
console is present exactly when the build that produced it ran, in development
and in production, with nothing to configure and nothing to get wrong.

Absent in a source checkout that has not built the frontend, which is the
ordinary case and not an error: the API serves normally and `/` is a 404.
"""


def create_app(lifespan=None, console_dir: Path | None = None) -> FastAPI:
    """Build the application. Adding a feature means adding a router here.

    Args:
        lifespan: Startup and shutdown behaviour, supplied by the entrypoint.
            ``None`` builds an application that assumes everything it needs is
            already running — the schema migrated, no job queue to open. That is
            what the tests want, and it is why the parameter exists rather than
            this module importing the real lifespan itself: composing a process
            is `entrypoints/`' job, not this one's.
        console_dir: Where to find a built console. Defaults to
            :data:`CONSOLE_DIR`. A parameter only so that a test can point at a
            directory it made; no deployment passes it.
    """
    app = FastAPI(title="bacteria", lifespan=lifespan)
    # First, and only because it reads that way in `/docs`: establishing a
    # session is the first thing a browser does, and the generated page lists
    # tags in the order routers are added.
    app.include_router(auth_router)
    app.include_router(chat_router)
    app.include_router(graph_router)
    app.include_router(ingestion_router)

    @app.get("/health", tags=["ops"])
    async def health() -> dict[str, str]:
        """Liveness only: the process is up and serving.

        Deliberately does not touch the database. A health check that fails when
        a dependency is down causes the orchestrator to restart a process that
        was working, which turns one outage into two.
        """
        return {"status": "ok"}

    _mount_console(app, CONSOLE_DIR if console_dir is None else console_dir)
    return app


def _mount_console(app: FastAPI, directory: Path) -> None:
    """Serve a built console at ``/``, if one was built.

    **Last, and everything above depends on it staying last.** A mount at ``/``
    matches every path no earlier route claimed, so a router added below this
    line would never receive a request — it would 404 through the static
    handler, with the route visible in `/docs` and dead in production. Starlette
    resolves in registration order and says nothing about the shadowing;
    `test_console_mount.py` asserts the API still wins, because a comment is not
    a guard.

    Mounted at the root rather than under `/console`, which the cookie decides
    rather than taste: [ADR 0005](../../../../docs/adr/0005-a-browser-holds-a-session-not-a-key.md)
    makes ``SameSite=Strict`` the CSRF answer, and that holds only while the
    console and the API share an origin. A separate origin needs CORS and a real
    token, so the mount and the auth decision are the same decision.

    ``html=True`` serves ``index.html`` for a directory request, which is what
    makes ``/`` work at all. It does not make deep links work: a console that
    routes client-side needs every unknown path to fall back to the index, and
    this returns 404 for them. That is honest for a console with tabs rather
    than URLs, and is the next thing to change if that stops being true.

    Silent when there is nothing to serve. A missing directory means the
    frontend has not been built, which is the ordinary state of a source
    checkout — warning about it would fire on every contributor's every boot,
    the failure the ASGI lifespan describes at length.
    """
    if not (directory / "index.html").is_file():
        return

    app.mount("/", StaticFiles(directory=directory, html=True), name="console")
