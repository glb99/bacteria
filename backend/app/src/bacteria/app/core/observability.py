"""Traces and metrics for this application, and deliberately not for the agent.

OpenTelemetry is the instrumentation, Logfire is where it goes; those are two
decisions and [ADR 0003](../../../../../docs/adr/0003-observability-is-opentelemetry-exported-to-logfire.md)
keeps them apart on purpose. The exporter is an OTLP endpoint, so replacing the
backend is a configuration change rather than an unpicking of instrumentation.

**Nothing here is imported by ``bacteria.agent``, and nothing in that package
imports this.** The agent is vendorable: its records travel into hosts that never
agreed to this application's observability vendor, and a tracing decorator on
``Runtime`` would carry one there. The instrumentation this module installs
reaches the agent's work anyway — by patching the *provider SDKs* and the
database driver the agent already uses — which is the whole trick. A host that
wants none of it simply never calls :func:`configure`.

**This is operational, not evidentiary.** ``run_meta`` in the transcript stays
the authoritative record of what a run did (the agent's ADR 0019), and every
deterministic eval keeps reading it. Spans answer questions about the *system* —
what was slow, what contended, what a turn cost — and nothing may become
answerable only by querying a vendor, because that answer would live outside the
single commit path ADR 0004 protects and would leave with a subscription.

Not built:
    Spans for the agent's own layers -- a model call, a tool execution, an
    assembly -- which is where the interesting shape of a turn is. Adding them
    means a protocol the agent declares and a host implements, with a no-op
    default, in the shape the agent's ADR 0024 used for retrieval. It is a
    separate record and not a widened import list.
"""

from __future__ import annotations

import logging
import warnings
from typing import Any, Awaitable, Callable

import logfire

from bacteria.app.core.settings import get_settings

logger = logging.getLogger(__name__)

_configured = False


def configure(service_name: str, *, console: bool = True) -> None:
    """Set up tracing for this process. Safe to call twice; the second is a no-op.

    ``service_name`` is what tells the API process and the worker apart on one
    timeline, which is the entire question ADR 0001 left open — a job and a
    request contending on the same loop are indistinguishable until something
    labels them.

    **No token means console output, not a refusal to boot**, and this is the one
    place the ``BACTERIA_`` prefix rule's "a typo refuses to start" behaviour
    would be actively wrong. A development machine with no token is the ordinary
    case rather than a misconfiguration, and failing there would make every
    contributor configure a vendor before running anything.

    ``console`` is how a surface opts out of that, and it exists because the
    admin CLI needed it within minutes of being instrumented. Its stdout is not
    a log — it is where a person reads what a model said, which is the same
    property the ``reconfigure`` call at the top of ``cli.main`` protects — and
    nine query spans printed between a question and its answer make the
    conversation unreadable. Spans are still produced and still exported when a
    token is set; only the printing stops.

    Called from entrypoints, which is where configuration belongs. Not from
    ``create_app``: a test that builds the application must not acquire an
    exporter as a side effect.
    """
    global _configured
    if _configured:
        return

    settings = get_settings()

    logfire.configure(
        service_name=service_name,
        console=None if console else False,
        # "if-token-present" is what makes absence a local-console run rather
        # than an error, and it is a Logfire behaviour rather than one this
        # module implements -- so there is no branch here that could disagree
        # with what the SDK actually does.
        send_to_logfire="if-token-present",
        token=settings.logfire_token or None,
        environment=settings.logfire_environment,
        # Scrubbing stays at its default, which is on. What keeps conversation
        # text out of the exporter is that nothing here creates a span carrying
        # it -- see the module docstring. Scrubbing is the second line, for the
        # attributes the integrations add on their own.
    )

    # Instrumented at the driver rather than at the repository, so it covers
    # every query in the process -- the API's, the worker's, and Alembic's --
    # without a single call site knowing about it.
    logfire.instrument_psycopg()

    _instrument_provider(settings.model_provider)

    _configured = True
    logger.info("observability configured for %r", service_name)


def _instrument_provider(provider: str) -> None:
    """Patch the model SDK this deployment is configured for, and only that one.

    **This is how token counts and model latency arrive without
    ``bacteria.agent`` importing anything.** The agent calls these libraries;
    this patches the libraries. The vendorable package is untouched and the gap
    the agent's ADR 0019 named -- "still unrecorded: latency and token cost" --
    closes from outside it.

    One provider, not both, and that was learned rather than designed. Calling
    every instrumentation unconditionally looked harmless and raised: each needs
    its own optional dependency, so a deployment without one crashes at startup
    over a provider it does not use. Two entrypoint tests caught it.

    An unknown provider is passed over in silence here. It is not this function's
    job to reject one -- ``build_model_client`` already refuses, by name, with the
    valid set in the message, and a second check would either duplicate that or
    disagree with it.
    """
    if provider == "anthropic":
        logfire.instrument_anthropic()
    elif provider == "gemini":
        logfire.instrument_google_genai()


def instrument_app(app: Any) -> None:
    """Add request spans to a FastAPI application.

    Separate from :func:`configure` because it needs the application object,
    which only an entrypoint has, while everything else is process-wide.

    **The suppressed warning is Logfire being right in general and wrong here.**
    It fires because this runs before :func:`configure`, which it has to: the
    caller instruments at module scope, since Starlette builds its middleware
    stack on the first call and the lifespan is already one. Logfire's own proxy
    tracer provider handles the ordering -- a spike watched real request spans
    arrive from exactly this arrangement -- so what is left is a warning that is
    printed on every boot and means nothing. Filtered by message rather than by
    class, because the class lives in ``logfire._internal``.
    """
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore", message="Instrumentation will have no effect", category=UserWarning
        )
        logfire.instrument_fastapi(app)


async def job_span(
    call_next: Callable[[], Awaitable[Any]],
    context: Any,
    _worker: Any,
) -> Any:
    """Wrap every job a worker runs in one span.

    A procrastinate *worker* middleware rather than a task middleware: it is
    always async and wraps both sync and async tasks, so no task can be added
    later that quietly escapes measurement.

    Registered in :mod:`bacteria.app.core.jobs`, which owns the shape of a job.
    Putting it on the task itself would spread the vendor into
    ``chat/tasks.py`` and every feature that grows one, and features own their
    tasks precisely so that nothing cross-cutting has to be repeated in them.

    This is the span ADR 0001 needs. Its "a blocking job stalls requests […] and
    nothing here would attribute the latency to the job" is unanswerable while a
    job's duration is not a measured thing sharing a timeline with the requests
    it competed with.
    """
    # `context.job.task_name`, not `context.task_name`. The first spike run
    # produced a timeline of spans all named "job unknown", which is a defensive
    # `getattr` doing exactly what it was written to do and hiding the mistake it
    # was written to survive.
    job = getattr(context, "job", None)
    with logfire.span(
        "job {task}",
        task=getattr(job, "task_name", "unknown"),
        job_id=getattr(job, "id", None),
        queue=getattr(job, "queue", None),
    ):
        return await call_next()
