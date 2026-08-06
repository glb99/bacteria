"""Chain of Responsibility: the structure a workflow is assembled from.

A workflow here is a sequence of steps, each of which decides for itself whether
it applies. :class:`Handler` is the link — it knows only about the next link.
:class:`StepHandler` is the one concrete link that matters: it hosts a
:class:`~fastpaip.core.protocols.Processable` and runs it when it applies.

The split is what makes a pipeline composable. Business logic implements
``Processable`` and knows nothing about chains, ordering, or what runs after it;
the chain knows nothing about what any step does. Assembling one is the only
place both facts are needed at once.

**The chain is async, and steps may be either.** ``handle`` is a coroutine
because a real workflow step does I/O — writes a batch, calls an API, asks a
model — and a synchronous chain forecloses all of it. But most steps are pure
transformations, and forcing their authors to write ``async def`` would be a tax
with no benefit, so a plain function is accepted and run in a worker thread.
That is the same rule the agent applies to tool handlers, deliberately: two
places in this codebase host caller-supplied callables, and they should not
disagree about what a callable may be.

This is *not* the same thing as the agent's runtime, and the two should not be
merged even though both sequence steps. ``bacteria``'s runtime tracks step
identity so that a retry provably cannot re-run a side effect that already
landed; a chain here has no such property and claims none. Chains are for
workflows — ingesting a batch, processing an upload, and eventually the ones an
agent proposes. A turn is not a workflow.
"""

import inspect
import logging
from abc import ABC, abstractmethod
from collections.abc import Awaitable
from typing import Any, Callable, Generic, TypeVar

import anyio.to_thread

from .protocols import DataType, Processable

logger = logging.getLogger(__name__)

_T = TypeVar("_T")


async def call_either(fn: Callable[..., "_T | Awaitable[_T]"], *args: Any) -> _T:
    """Call ``fn``, awaiting it or threading it depending on what it is.

    ``inspect.iscoroutinefunction`` is asked about the function rather than
    checking whether the *result* is awaitable, because the latter would have
    already run a synchronous callable on the event loop by the time it could
    tell — the check has to happen before the call, not after it.
    """
    if inspect.iscoroutinefunction(fn):
        return await fn(*args)  # type: ignore[misc]
    return await anyio.to_thread.run_sync(fn, *args)  # type: ignore[arg-type]


class Handler(Generic[DataType], ABC):
    """One link in a chain, holding a reference to the next.

    Stateful by design: its job is to hold the shape of the pipeline.
    """

    def __init__(self) -> None:
        # An instance attribute, set here rather than declared on the class.
        # As a class attribute it appeared to work — `set_next` assigns to
        # `self`, which shadows it — but every handler that had not yet been
        # given a successor was reading one shared default, and any code
        # inspecting `_next_handler` before `set_next` saw the class's value
        # rather than that instance's.
        self._next_handler: "Handler[DataType] | None" = None

    def set_next(self, handler: "Handler[DataType]") -> "Handler[DataType]":
        """Link ``handler`` after this one.

        Returns:
            ``handler``, not ``self``, so chains read in execution order:
            ``a.set_next(b).set_next(c)`` runs a, then b, then c. Returning
            ``self`` would let the same expression build the chain backwards.
        """
        self._next_handler = handler
        return handler

    @abstractmethod
    async def handle(self, data: DataType) -> DataType:
        """Process ``data`` and pass it to the next link.

        Subclasses do their own work and then await ``super().handle()`` to
        continue the chain. A subclass that forgets ends the chain silently,
        which is the one mistake this design makes easy — there is no
        "unreached step" signal.
        """
        if self._next_handler:
            return await self._next_handler.handle(data)
        return data


class StepHandler(Handler[DataType]):
    """A link that runs one :class:`~fastpaip.core.protocols.Processable`.

    The bridge between the chain's structure and the application's logic: it is
    the only place the two meet, which is why business logic never imports this
    module and this module never knows what any step does.
    """

    def __init__(self, processor: Processable[DataType]) -> None:
        super().__init__()
        self._processor = processor

    async def handle(self, data: DataType) -> DataType:
        """Run the processor if it applies, then continue down the chain.

        A step that declines is logged rather than passed over silently. In a
        pipeline of any length, "nothing happened and nothing said so" is the
        hardest failure to diagnose — the output is simply wrong, with no record
        of which step chose not to act. Note the log says *that* a step declined
        and not *why*; see the limitation on ``Processable.can_handle``.
        """
        processed_data = data
        name = type(self._processor).__name__
        if await call_either(self._processor.can_handle, data):
            logger.debug("running processor", extra={"processor": name})
            processed_data = await call_either(self._processor.process, data)
        else:
            logger.debug("processor declined", extra={"processor": name})

        return await super().handle(processed_data)
