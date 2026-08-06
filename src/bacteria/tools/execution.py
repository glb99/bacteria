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

from dataclasses import dataclass
from typing import Any, Callable

from bacteria.model.protocol import ToolCall
from bacteria.tools.registry import ToolRegistry, UnknownToolError


class ToolExecutionError(Exception):
    """A proposed tool call did not execute, for any reason.

    Covers unknown tool, rejected by approval, and handler raised. One type for
    all three because callers treat them identically — the run stops and the
    attempt is recorded. The specific cause is in the message and in the
    chained ``__cause__``.
    """


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


def execute_tool_call(
    tool_call: ToolCall,
    registry: ToolRegistry,
    approve: Callable[[ToolCall], bool] = lambda _tool_call: True,
) -> ToolResult:
    """Resolve, approve, then run a single proposed tool call.

    Args:
        tool_call: The model's proposal. Untrusted: the name may not exist and
            the arguments are whatever the model produced.
        registry: Where the name is resolved to a real handler.
        approve: The gate. Defaults to allow-everything, which is right for
            tests and wrong for anything with a user attached — the CLI passes
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
        raise ToolExecutionError(f"unknown tool: {name}") from exc

    # Before the handler is touched, not after. A gate that reports on an
    # action already taken is not a gate.
    if not approve(tool_call):
        raise ToolExecutionError(f"tool call rejected: {name}")

    try:
        output = tool.handler(tool_call["input"])
    except Exception as exc:
        raise ToolExecutionError(f"tool handler failed: {name}") from exc

    return ToolResult(tool_call_id=tool_call["id"], name=name, output=output)
