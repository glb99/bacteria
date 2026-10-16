import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NotRequired, TypedDict, TypeVar

import anyio

from agent.errors import ToolExecutionError, UnknownToolError

_T = TypeVar("_T")


class ToolCall(TypedDict):
    """A tool invocation the model asked for. Asking is not authority to run.

    A model client's only job with a tool call is to report it. Executing one
    happens in :func:`bacteria.tools.execution.execute_tool_call`, which no
    model client imports — the separation is structural, not conventional.

    Attributes:
        id: Correlates this call with the ``tool_result`` sent back to the
            model afterwards. Providers that do not issue their own ids get a
            synthetic one from the client that produced the call.
        name: Must match a tool registered in a :class:`~bacteria.tools.registry.ToolRegistry`;
            an unregistered name is an error, never a fallback.
        input: Arguments as the model produced them. Untrusted — a schema-valid
            payload is a well-shaped payload, not a correct or safe one.
        provider_data: Opaque provider state that must survive a round trip
            back to that same provider, carried through the runtime unread.
            Gemini's ``thought_signature`` is the motivating case: omit it on
            the follow-up call and the provider rejects the request outright.
            Deliberately not named after any one provider so that a module
            which does not care about it does not have to know it exists.
    """

    id: str
    name: str
    input: dict[str, Any]
    provider_data: NotRequired[dict[str, Any]]


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
        (:mod:`bacteria.agent.interfaces.cli`), and worth revisiting if it does not.
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


async def _call_either(fn: Callable[..., _T | Awaitable[_T]], *args: Any) -> _T:
    """Call ``fn``, awaiting it or threading it depending on what it is."""

    if inspect.iscoroutinefunction(fn):
        return await fn(*args)
    return await anyio.to_thread.run_sync(fn, *args)


async def execute_tool_call(
    tool_call: ToolCall, tool_registry: ToolRegistry
) -> ToolResult:
    name = tool_call["name"]

    try:
        tool = tool_registry.get(name)
    except UnknownToolError as exc:
        raise ToolExecutionError(
            f"Unknown tool: {name}", reason="unknown_tool"
        ) from exc

    output = await _call_either(tool.handler, tool_call["input"])

    return ToolResult(tool_call_id=tool_call["id"], name=name, output=output)


DEFAULT_NOTES_PATH = Path(".proteria/notes.txt")


def build_add_note_tool(notes_path: Path = DEFAULT_NOTES_PATH) -> ToolDefinition:
    def handler(tool_input: dict[str, Any]) -> str:
        text = tool_input["text"]
        notes_path.parent.mkdir(parents=True, exist_ok=True)
        with notes_path.open("a", encoding="utf-8") as f:
            f.write(text + "\n")
        return f"saved note: {text}"

    return ToolDefinition(
        name="add_note",
        description="Appends a short note to a local notes file, for the user to read later.",
        input_schema={
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "The note text to save."}
            },
            "required": ["text"],
        },
        handler=handler,
    )
