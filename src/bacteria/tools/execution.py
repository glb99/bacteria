"""Tool execution — the seam Part 6 names directly: "the model asks, the
system acts." This module is the only place a tool's handler actually gets
called. Deliberately separate from bacteria.model.client, which only ever
reports a tool_use block and never acts on it (see
test_tool_calls_are_surfaced_as_proposals_not_executed) — and separate from
bacteria.runtime.runtime, which decides *when* execution happens in a turn,
not how a given call is authorized or run.

`approve` is named here only as the smallest possible hook, not designed in
depth. Part 7 ("Execution Surfaces, Identity, and Approval Boundaries") is
where authorization/approval get a real design. Defaulting to "always allow"
is a provisional stub — flagged here, not a security decision to build on.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from bacteria.tools.registry import ToolRegistry, UnknownToolError


class ToolExecutionError(Exception):
    """A proposed tool call could not be executed: unknown tool, rejected by
    approval, or the handler itself raised."""


@dataclass
class ToolResult:
    tool_call_id: str
    name: str
    output: Any


def execute_tool_call(
    tool_call: dict[str, Any],
    registry: ToolRegistry,
    approve: Callable[[dict[str, Any]], bool] = lambda _tool_call: True,
) -> ToolResult:
    name = tool_call["name"]
    try:
        tool = registry.get(name)
    except UnknownToolError as exc:
        raise ToolExecutionError(f"unknown tool: {name}") from exc

    if not approve(tool_call):
        raise ToolExecutionError(f"tool call rejected: {name}")

    try:
        output = tool.handler(tool_call["input"])
    except Exception as exc:
        raise ToolExecutionError(f"tool handler failed: {name}") from exc

    return ToolResult(tool_call_id=tool_call["id"], name=name, output=output)
