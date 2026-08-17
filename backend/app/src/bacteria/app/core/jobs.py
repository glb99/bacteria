"""The job queue: work that outlives the request that asked for it.

Backed by Postgres rather than a broker, and that is the decision worth
understanding before changing it.

**Why not Redis or SQS.** Both introduce the same gap: you commit the row, then
you enqueue the job. If the process dies in between, the work is gone and there
is no record it was ever meant to happen. That failure is exactly the one this
codebase is otherwise organized against — ingestion stores rejections rather
than counting them, the runtime commits evidence before re-raising, and a test
exists so schema drift cannot be silent. Adopting a queue that can drop work
quietly would contradict all of it.

Procrastinate enqueues **inside the caller's transaction**, so a job and the
data change that justifies it commit together or not at all. That is a
correctness property, not a convenience, and it is the whole reason for the
choice.

**What it costs.** Queue throughput shares the primary database. At high enough
volume that becomes the wrong shape and a real broker is warranted — but "high
enough" is far past anything here, and the move is contained, because handlers
are ordinary functions and only the transport changes.

**What this is not.** A queue answers "run this later". It does not answer
"resume this run where it paused", which is what an agent turn waiting on
human approval needs. That is durable execution, a different mechanism, and
building this does not unblock it. See the approval gap in
``bacteria.agent.tools.approval``.

Not built:
    Scheduled and periodic jobs. Procrastinate supports cron-style scheduling
    and nothing here uses it. When something does, it belongs in the worker
    entrypoint rather than here — this module owns the shape of a job, not the
    calendar.

    Dead-letter handling. A job that exhausts its retries stays failed in the
    table, where it can be found by query but nothing surfaces it. What is
    missing is a route or an alert, not a mechanism.
"""

from functools import lru_cache
from typing import Any

import psycopg_pool
from procrastinate import App, PsycopgConnector

from bacteria.app.core import observability
from bacteria.app.core.settings import get_settings


def _psycopg_dsn(database_url: str) -> str:
    """Strip SQLAlchemy's dialect prefix, which psycopg does not understand.

    SQLAlchemy wants ``postgresql+psycopg://``; psycopg wants ``postgresql://``.
    One setting names the database and both consumers derive from it, because
    two URLs in configuration is two databases waiting to disagree.
    """
    return database_url.replace("+psycopg", "", 1)


def _pool_factory(**kwargs: Any) -> psycopg_pool.AsyncConnectionPool:
    """Build the pool, reading the database URL only when one is opened.

    The indirection exists to keep a promise :mod:`bacteria.app.core.settings`
    makes: importing a module must not read configuration. Procrastinate
    discovers tasks by import, and a task module has to reference the app to
    register itself — so if building the app read settings, importing any task
    would freeze process-wide configuration at import time.

    That is not hypothetical. It happened: the API tests monkeypatch the model
    provider, pytest imports every test module before running any of them, and
    the settings were cached during collection with the real environment. The
    tests then called the live Anthropic API instead of the fake.
    """
    return psycopg_pool.AsyncConnectionPool(
        conninfo=_psycopg_dsn(get_settings().database_url), **kwargs
    )


@lru_cache
def get_app() -> App:
    """Return the process-wide Procrastinate app.

    Cached so that one connection pool serves the process. Tasks are registered
    against this app by importing the modules that define them — see
    :func:`register_tasks`.

    Constructing this touches no configuration and opens no connection; both
    happen when the pool is first opened.

    The worker middleware is registered here rather than on each task, so a task
    added later cannot escape measurement by forgetting a decorator. It produces
    no spans in a process that never called
    :func:`bacteria.app.core.observability.configure` -- which is why declaring
    it costs a test nothing.
    """
    return App(
        connector=PsycopgConnector(pool_factory=_pool_factory),
        # Through `worker_defaults` rather than a constructor argument, which is
        # where procrastinate puts anything a `run_worker_async` call could also
        # pass. A default rather than an argument at the call site: there are two
        # of those -- `bacteria-worker` and the in-API lifespan -- and they must
        # not be able to differ on whether jobs are measured.
        worker_defaults={"worker_middleware": [observability.job_span]},
    )


def register_tasks() -> App:
    """Import every module that defines a task, and return the app.

    Procrastinate discovers tasks by import side effect, so a worker that never
    imports a task module reports "unknown task" for jobs it is perfectly able
    to run — and a *producer* that never imports it cannot enqueue at all.
    Doing it in one named place means the failure is impossible rather than
    dependent on which entrypoint happened to import what.
    """
    from bacteria.app.chat import tasks as _chat_tasks  # noqa: F401
    from bacteria.app.ingestion import tasks as _ingestion_tasks  # noqa: F401

    return get_app()
