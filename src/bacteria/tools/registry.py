"""Tool registry — Part 6 (Tools, MCP, and Capability Surfaces).

Owns the capability surface: which local tools exist, and which of them are
exposed to the model for a given run. MCP is deliberately out of scope (see
docs/SYSTEM_DESIGN.md, Part 6) — every tool here is a local Python callable
the application owns directly, not something reached through an external
protocol/server.

A ToolDefinition's handler never crosses into the model-facing schema
(`to_schema()`) — the model only ever sees name/description/input_schema,
never anything capable of running code. That split is what keeps "the model
asks" (this module) and "the system acts" (bacteria.tools.execution) as two
separate modules rather than one.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[[dict[str, Any]], Any]

    def to_schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }


class UnknownToolError(KeyError):
    """A tool call (or a filter) named a tool the registry doesn't have."""


class ToolRegistry:
    """Filters what's exposed per run — checklist item 1 from Part 6: 'expose
    only tools needed for this specific user, tenant, workflow stage, task,'
    not the whole registry by default."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, tool: ToolDefinition) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> ToolDefinition:
        try:
            return self._tools[name]
        except KeyError:
            raise UnknownToolError(name) from None

    def schemas_for_run(self, allowed: list[str] | None = None) -> list[dict[str, Any]]:
        """Model-facing schemas only. `allowed` narrows exposure for this run;
        omitting it exposes everything registered — callers that actually
        have per-run/per-user scoping should pass it explicitly."""
        names = allowed if allowed is not None else list(self._tools)
        return [self._tools[name].to_schema() for name in names if name in self._tools]
