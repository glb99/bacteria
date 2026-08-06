"""The capability surface: what tools exist, and which the model gets told about.

This module answers "what could be called". It has no answer for "may this be
called now" — that is :mod:`bacteria.tools.approval` — and it cannot call
anything itself — that is :mod:`bacteria.tools.execution`. Describing a
capability and holding authority to use it are separate concerns, and they are
separate modules here so that the separation cannot erode by accident.

Invariant: the handler never reaches the model. :meth:`ToolDefinition.to_schema`
returns name, description, and input schema, and nothing that can run code. The
callable and its description live on the same object but leave it through
different doors.

Not built:
    MCP. Every tool here is a local Python callable this application owns. MCP
    is worth its cost when integrating a growing or third-party set of external
    systems and wanting standardized discovery across them; for a fixed set of
    first-party functions it adds a transport, a process or origin trust
    surface, and a protocol version to track, in exchange for interop nothing
    needs. If adopted, the role would be MCP *client* — this system is the one
    that wants capabilities, not the one exposing them. It would attach as an
    alternative source of ``ToolDefinition`` objects feeding ``register``, so
    execution and approval would not change — name, description, and input
    schema map over directly, with the handler becoming an RPC call. The cost of
    staying local is that no third-party MCP server can be used, so any
    capability someone else already built has to be reimplemented here; that
    cost grows with the appetite for integrations.

    Policy behind ``schemas_for_run``. The narrowing mechanism exists; nothing
    decides what to narrow *to*. Real policy would key off the caller's identity,
    tenant, or workflow stage, none of which this system currently has.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class ToolDefinition:
    """A tool's public description and its private implementation, together.

    Attributes:
        name: The identifier the model uses to call it. Unique within a registry.
        description: Written for the model, since this is most of what it has to
            decide with. Vague descriptions produce wrong tool choices, and that
            failure looks like a model problem rather than a docs problem.
        input_schema: JSON Schema for the arguments. Constrains what the model
            is likely to send; validates nothing on the way back in — a
            well-shaped argument can still be a wrong one.
        handler: The callable that does the work. Takes the raw input dict and
            returns anything stringifiable. Never serialized, never sent
            anywhere; see :meth:`to_schema`.
    """

    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[[dict[str, Any]], Any]

    def to_schema(self) -> dict[str, Any]:
        """Render the model-facing view: description without capability.

        Explicitly listing the three fields, rather than deriving them by
        excluding ``handler``, means a field added to this dataclass later is
        not exposed to the model until someone decides it should be.
        """
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }


class UnknownToolError(KeyError):
    """A lookup named a tool the registry does not have.

    Usually a model hallucinating a plausible tool name. Raised rather than
    resolved by fuzzy match: guessing which real tool was meant turns a clear
    failure into a call the caller never asked for.
    """


class ToolRegistry:
    """Holds tool definitions and controls what each run gets to see.

    Exposure is a per-run decision, not a global one, which is why the read
    method is :meth:`schemas_for_run` rather than a plain ``all()``. Everything
    a model can see, it will eventually try.
    """

    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, tool: ToolDefinition) -> None:
        """Add a tool, replacing any existing tool of the same name.

        Last registration wins, which makes overriding a tool in a test
        straightforward. It also means a duplicate name silently shadows —
        acceptable while registration happens in one place
        (:mod:`bacteria.interfaces.cli`), and worth revisiting if it does not.
        """
        self._tools[tool.name] = tool

    def get(self, name: str) -> ToolDefinition:
        """Look up a tool by name, including its handler.

        Raises:
            UnknownToolError: No such tool.
        """
        try:
            return self._tools[name]
        except KeyError:
            raise UnknownToolError(name) from None

    def schemas_for_run(self, allowed: list[str] | None = None) -> list[dict[str, Any]]:
        """Return the model-facing schemas for one run.

        Args:
            allowed: Names to expose. Omitting it exposes everything registered,
                which is a convenience for a single-user deployment and not a
                sensible default once runs differ in what they should reach.
                Unknown names are skipped rather than raising, so a stale
                allow-list narrows exposure instead of breaking the run.

        Returns:
            Schemas only. No handler is reachable from anything returned here.
        """
        names = allowed if allowed is not None else list(self._tools)
        return [self._tools[name].to_schema() for name in names if name in self._tools]
