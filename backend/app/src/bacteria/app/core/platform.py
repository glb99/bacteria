"""Platform accommodations, in one place so they are findable.

Nothing here is architecture. It exists because a supported development
platform behaves differently from the deployment target, and burying that in an
entrypoint makes it look like a mistake to whoever reads it next.
"""

import asyncio
import sys
from collections.abc import Callable, Coroutine
from typing import Any, TypeVar

_T = TypeVar("_T")


def event_loop_factory() -> Callable[[], asyncio.AbstractEventLoop] | None:
    """The loop class to use, or ``None`` to accept the default.

    Windows defaults to ``ProactorEventLoop``, and psycopg's async mode refuses
    to run on it — every connection raises ``InterfaceError`` before a query is
    sent. The selector loop, which every other platform already uses, works.

    Returned as a factory rather than applied as a policy, deliberately.
    ``asyncio.set_event_loop_policy`` looks like the obvious fix and is not:
    ``asyncio.run`` takes an explicit ``loop_factory``, and anything passing one
    silently wins over the policy. uvicorn does exactly that — its
    ``asyncio_loop_factory`` hardcodes ``ProactorEventLoop`` on Windows — so a
    policy set before calling it has no effect whatsoever. That was not
    theoretical; it was diagnosed by watching the server keep failing after the
    policy was set.
    """
    if sys.platform == "win32":
        return asyncio.SelectorEventLoop
    return None


def run(coroutine: Coroutine[Any, Any, _T]) -> _T:
    """``asyncio.run`` with a loop the database driver can actually use.

    Every entrypoint that starts a loop goes through here, so there is one
    answer to "which loop does this process use" rather than one per process.
    """
    return asyncio.run(coroutine, loop_factory=event_loop_factory())
