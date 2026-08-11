"""The one place a tool handler actually runs. The model asks; this acts.

Every other module is structurally incapable of executing a tool. A model
client only reports that one was requested. The registry only holds the
callable. The runtime decides *when* execution happens but delegates *how* to
this function. Concentrating it here means the question "what can cause a side
effect in this system?" has a single-file answer, and every guard that should
apply to a side effect has exactly one place to live.

Order of operations in :func:`execute_tool_call` is itself a guarantee: resolve,
then approve, then run. Approval is checked after the tool is known — so the
prompt can describe a real tool rather than an unresolved name — and before the
handler is touched, so a rejection means nothing happened rather than something
happened and was reported as refused.

Invariant: a synchronous handler never runs on the event loop thread. Handlers
and approval gates may be written either way and this module absorbs the
difference — a coroutine is awaited, a plain function is run in a worker
thread. The asymmetry is deliberate: most tools are a dict lookup or a file
append, and requiring their authors to write ``async def`` would be a tax with
no benefit. But a synchronous handler called directly would stall every other
turn in the process for its duration, and that failure is invisible in a test
and in a single-user CLI — it appears only when two requests overlap, which is
why it is asserted rather than trusted.

Not built:
    Isolation. A handler runs in this process with this process's full
    privileges. Approval answers "should this happen"; it does nothing about
    "how far the damage reaches if it goes wrong". Those are different
    controls and only one exists. A real sandbox — subprocess, container,
    restricted filesystem — would wrap the handler call below. Until then,
    every registered tool is trusted first-party code, and that assumption is
    the security model.

    Timeouts and resource limits. A handler that blocks forever blocks the
    turn.

    Untrusted-content handling. Tool output flows back to the model as
    ``tool_result`` with no marking. If a tool ever returns content from an
    untrusted source — a fetched web page, someone else's document — that
    content must not be able to authorize the next action. Nothing here
    enforces that distinction yet, so the current tool set has to stay one
    where it does not arise.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Literal, TypeVar

import anyio.to_thread

from bacteria.model.protocol import ToolCall
from bacteria.tools.registry import ToolRegistry, UnknownToolError

_T = TypeVar("_T")

Approve = Callable[[ToolCall], "bool | Awaitable[bool]"]
"""The approval gate's shape: either a plain predicate or a coroutine function.

Both are allowed because the two real implementations differ in kind. An
interactive gate answers from a terminal and is naturally synchronous; a
service's gate has to persist a pending decision and await someone answering it
minutes later, which cannot be expressed synchronously at all.
"""


async def _call_either(fn: Callable[..., _T | Awaitable[_T]], *args: Any) -> _T:
    """Call ``fn``, awaiting it or threading it depending on what it is.

    ``inspect.iscoroutinefunction`` is asked about the function rather than
    checking whether the *result* is awaitable, because the latter would have
    already run a synchronous callable on the event loop by the time it could
    tell — the check has to happen before the call, not after it.
    """
    if inspect.iscoroutinefunction(fn):
        return await fn(*args)  # type: ignore[misc]
    return await anyio.to_thread.run_sync(fn, *args)  # type: ignore[arg-type]


ToolFailureReason = Literal["unknown_tool", "rejected", "handler_error"]
"""Why a proposed call did not run.

A closed set, so a new way to fail is a typed change that surfaces every reader
rather than a new string appearing in stored evidence nobody expected.
"""


class ToolExecutionError(Exception):
    """A proposed tool call did not execute, for any reason.

    Covers unknown tool, rejected by approval, and handler raised. One type for
    all three because callers treat them identically — the run stops and the
    attempt is recorded.

    Attributes:
        reason: Which of the three it was, as a value rather than a message
            prefix. "The model was refused" and "the model's tool broke" are
            the same outcome to control flow and entirely different events to
            anyone auditing the run — the first says a boundary held, the
            second says a boundary was never reached. Recovering that
            distinction by matching on the message string would make the
            transcript's meaning depend on the wording of an error.
    """

    def __init__(self, message: str, reason: ToolFailureReason) -> None:
        super().__init__(message)
        self.reason = reason


@dataclass
class ToolResult:
    """What a successfully executed tool produced.

    Attributes:
        tool_call_id: Carried through from the proposal, so the result can be
            correlated back to the call in the follow-up model request.
        name: The tool that ran.
        output: Whatever the handler returned. Stringified when sent to the
            model; not otherwise interpreted.
    """

    tool_call_id: str
    name: str
    output: Any


async def execute_tool_call(
    tool_call: ToolCall,
    registry: ToolRegistry,
    approve: Approve = lambda _tool_call: True,
) -> ToolResult:
    """Resolve, approve, then run a single proposed tool call.

    Args:
        tool_call: The model's proposal. Untrusted: the name may not exist and
            the arguments are whatever the model produced.
        registry: Where the name is resolved to a real handler.
        approve: The gate, synchronous or not — see :data:`Approve`. Defaults to
            allow-everything, which is right for tests and wrong for anything
            with a user attached — the CLI passes
            :func:`bacteria.tools.approval.cli_approve` instead. The default is
            permissive rather than restrictive because a default-deny would make
            every test assert its way past the gate, and the real deployment
            path overrides it explicitly.

    Returns:
        The handler's output, wrapped for correlation.

    Raises:
        ToolExecutionError: Unknown tool, rejected, or the handler raised. A
            handler exception is wrapped rather than propagated so that callers
            can catch one type; the original is preserved as ``__cause__``.
    """
    name = tool_call["name"]
    try:
        tool = registry.get(name)
    except UnknownToolError as exc:
        raise ToolExecutionError(f"unknown tool: {name}", reason="unknown_tool") from exc

    # Before the handler is touched, not after. A gate that reports on an
    # action already taken is not a gate. Note this stays outside the try below:
    # a gate that raises is a broken gate, and must not be reported as a failed
    # tool call — that would be indistinguishable from a refusal.
    if not await _call_either(approve, tool_call):
        raise ToolExecutionError(f"tool call rejected: {name}", reason="rejected")

    try:
        output = await _call_either(tool.handler, tool_call["input"])
    except Exception as exc:
        raise ToolExecutionError(f"tool handler failed: {name}", reason="handler_error") from exc

    return ToolResult(tool_call_id=tool_call["id"], name=name, output=output)
