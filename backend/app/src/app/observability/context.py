from contextvars import ContextVar

from bacteria.entities.event import Event
from bacteria.entities.job import Job

_job_id: ContextVar[str | None] = ContextVar("job_id", default=None)
_trace_id: ContextVar[str | None] = ContextVar("trace_id", default=None)
_queue: ContextVar[str | None] = ContextVar("queue", default=None)
_event_type: ContextVar[str | None] = ContextVar("event_type", default=None)
_sender_id: ContextVar[str | None] = ContextVar("sender_id", default=None)


def bind_job(job: Job) -> None:
    # trace_id = job.id so every log line during a job shares the same trace
    _job_id.set(str(job.id))
    _trace_id.set(str(job.id))
    _queue.set(job.queue)
    _event_type.set(job.payload.get("event_type"))


def bind_event(event: Event) -> None:
    _sender_id.set(event.sender_id)


def bind_request(request_id: str) -> None:
    # trace_id comes from the x-request-id HTTP header, or a generated UUID if absent
    _trace_id.set(request_id)


def clear() -> None:
    _job_id.set(None)
    _trace_id.set(None)
    _queue.set(None)
    _event_type.set(None)
    _sender_id.set(None)


def get_context() -> dict:
    return {
        k: v
        for k, v in {
            "job_id": _job_id.get(),
            "trace_id": _trace_id.get(),
            "queue": _queue.get(),
            "event_type": _event_type.get(),
            "sender_id": _sender_id.get(),
        }.items()
        if v is not None
    }
