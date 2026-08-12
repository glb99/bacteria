"""ASGI entrypoint: configuration, and nothing else.

Everything here is a deployment decision — build the app, set the log level,
and start a server. The logic being configured lives elsewhere.

``app`` is importable by any ASGI server, which is how a Linux deployment runs
it. :func:`main` exists as well, and on Windows it is the only thing that works:
psycopg's async mode cannot run on the default event loop there, and a server
launched externally has already created one by the time it imports this module.
Choosing the loop has to happen in a process we own, before the server library
starts. See :mod:`fastpaip.core.platform`.

Note what this does *not* do: create tables. The schema belongs to Alembic, and
a deployment runs ``alembic upgrade head`` before starting this process. An
application that builds its own schema on boot will, the first time a model
changes, start successfully against a database that is missing a column and fail
later at the query — which is a worse failure than refusing to start.
"""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from fastpaip.core import platform
from fastpaip.core.jobs import register_tasks
from fastpaip.core.settings import get_settings, load_env_file
from fastpaip.views import create_app

# First, and before settings are read. Provider SDKs look for their keys in the
# real environment under unprefixed names, which nothing else puts there; see
# `load_env_file`. An entrypoint is the right place for it because this is where
# the process is composed, and the wrong place for it is anywhere importable.
load_env_file()

settings = get_settings()
logging.basicConfig(level=settings.log_level)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Hold the job queue open for the life of the process.

    Procrastinate needs its connection pool open before anything can enqueue,
    and it has to stay open for the life of the process rather than being set up
    once at boot -- which is why this is a context manager wrapping the yield.
    Without it, every deferral fails with ``AppNotOpen`` at request time rather
    than at boot, which is the wrong end to find out.

    Opening it here rather than per request means one pool for the process.
    """
    async with register_tasks().open_async():
        yield


app = create_app(lifespan=lifespan)


def main() -> int:
    """Run a development server on an event loop psycopg can use.

    Drives ``Server.serve()`` rather than calling ``uvicorn.run()``, because
    ``Server.run()`` supplies its own ``loop_factory`` -- ``ProactorEventLoop``
    on Windows -- and psycopg cannot use it. Going through
    :func:`fastpaip.core.platform.run` is the only way to choose the loop.
    """
    import uvicorn

    config = uvicorn.Config(
        # By import string rather than by object, so a reloader could re-import
        # it in a fresh process.
        "fastpaip.entrypoints.asgi:app",
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "8000")),
        log_level=settings.log_level.lower(),
    )
    platform.run(uvicorn.Server(config).serve())
    return 0


__all__ = ["app", "main"]


if __name__ == "__main__":
    raise SystemExit(main())
