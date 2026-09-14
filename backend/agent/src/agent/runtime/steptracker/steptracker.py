from typing import Any, Awaitable, Callable

from backend.agent.src.agent.runtime.steptracker.error import StepAlreadyExecutedError


class StepTracker:
    """Remembers which steps have run, so none can run twice in one run.

    Deliberately minimal: a set of ids, no persistence, no results cache. It
    provides idempotency *within* a run and claims nothing beyond that — after
    the run returns, the tracker is discarded along with everything it knew.
    Durable idempotency is a different mechanism and is not built.
    """

    def __init__(self) -> None:
        self._executed: set[str] = set()

    def has_run(self, step_id: str) -> bool:
        """Whether ``step_id`` has already executed in this run."""
        return step_id in self._executed

    async def run_once(self, step_id: str, fn: Callable[[], Awaitable[Any]]) -> Any:
        """Await ``fn()``, or refuse if ``step_id`` already ran.

        The id is recorded only after ``fn`` returns. A step that raises is
        therefore not marked as executed — but nothing retries it either, so
        this is about honest bookkeeping rather than a retry policy. A real
        retry would need to know whether the failure happened before or after
        the side effect landed, which this cannot tell.

        Note what this does *not* protect against, now that ``fn`` is awaited:
        the check and the recording are separated by a suspension point, so two
        coroutines sharing one tracker could both pass the check before either
        recorded itself. That race cannot arise today because a tracker is
        created per run and never leaves it — the guarantee is single-run
        idempotency, and it rests on that ownership rather than on any locking
        here. Sharing a tracker across concurrent runs would silently void it.

        Raises:
            StepAlreadyExecutedError: ``step_id`` already ran.
        """
        if self.has_run(step_id):
            raise StepAlreadyExecutedError(step_id)
        result = await fn()
        self._executed.add(step_id)
        return result
