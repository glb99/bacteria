"""ASGI entrypoint: configuration, and nothing else.

Everything here is a deployment decision — build the app, set the log level,
and start a server. The logic being configured lives elsewhere.

``app`` is importable by any ASGI server, which is how a Linux deployment runs
it. :func:`main` exists as well, and on Windows it is the only thing that works:
psycopg's async mode cannot run on the default event loop there, and a server
launched externally has already created one by the time it imports this module.
Choosing the loop has to happen in a process we own, before the server library
starts. See :mod:`bacteria.app.core.platform`.

Note what this does *not* do: create tables. The schema belongs to Alembic, and
a deployment runs ``alembic upgrade head`` before starting this process. An
application that builds its own schema on boot will, the first time a model
changes, start successfully against a database that is missing a column and fail
later at the query — which is a worse failure than refusing to start.
"""

import asyncio
import contextlib
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from bacteria.app.core import platform
from bacteria.app.core.jobs import register_tasks
from bacteria.app.core.settings import get_settings, load_env_file
from bacteria.app.views import create_app

logger = logging.getLogger(__name__)

# First, and before settings are read. Provider SDKs look for their keys in the
# real environment under unprefixed names, which nothing else puts there; see
# `load_env_file`. An entrypoint is the right place for it because this is where
# the process is composed, and the wrong place for it is anywhere importable.
load_env_file()

settings = get_settings()
logging.basicConfig(level=settings.log_level)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Hold the job queue open, and optionally run a worker beside the API.

    Procrastinate needs its connection pool open before anything can enqueue,
    and it has to stay open for the life of the process rather than being set up
    once at boot -- which is why this is a context manager wrapping the yield.
    Without it, every deferral fails with ``AppNotOpen`` at request time rather
    than at boot, which is the wrong end to find out.

    Opening it here rather than per request means one pool for the process.

    The worker is started only when ``run_worker_in_api`` is set, and this stays
    an entrypoint's job rather than a feature's: it decides *which processes this
    deployment has*, which is the same kind of question as which port to bind.
    What it is not is a good idea in general -- see the setting's own
    documentation and ADR 0001. It exists for platforms that run one process, and
    the honest comparison there is not against a separate worker but against no
    worker at all.
    """
    settings = get_settings()
    # The app object, not whatever `open_async` yields -- `queue_worker.py` uses
    # it this way and the two must not disagree about what "the queue" is.
    queue = register_tasks()
    async with queue.open_async():
        if not settings.run_worker_in_api:
            yield
            return

        logger.warning(
            "running the job worker inside the API process (concurrency=%d); "
            "a worker failure can now take the API with it",
            settings.worker_concurrency,
        )
        worker = asyncio.create_task(
            queue.run_worker_async(concurrency=settings.worker_concurrency),
            name="in-api-procrastinate-worker",
        )
        try:
            yield
        finally:
            # Cancelled and awaited, not abandoned. An un-awaited task is
            # destroyed with a warning and whatever job it held stays marked
            # `doing` -- so the row is invisible to the next worker and to
            # anyone reading the table for stuck work.
            worker.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await worker


app = create_app(lifespan=lifespan)


def main() -> int:
    """Run a development server on an event loop psycopg can use.

    Drives ``Server.serve()`` rather than calling ``uvicorn.run()``, because
    ``Server.run()`` supplies its own ``loop_factory`` -- ``ProactorEventLoop``
    on Windows -- and psycopg cannot use it. Going through
    :func:`bacteria.app.core.platform.run` is the only way to choose the loop.
    """
    import uvicorn

    config = uvicorn.Config(
        # By import string rather than by object, so a reloader could re-import
        # it in a fresh process.
        "bacteria.app.entrypoints.asgi:app",
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "8000")),
        log_level=settings.log_level.lower(),
    )
    platform.run(uvicorn.Server(config).serve())
    return 0


__all__ = ["app", "main"]


if __name__ == "__main__":
    raise SystemExit(main())
