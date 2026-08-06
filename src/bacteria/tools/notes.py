"""A worked example of a tool: small, real, and reversible.

``add_note`` appends a line to a local text file. It is trivial on purpose, but
not a no-op on purpose either — the approval boundary only proves anything when
what it gates would genuinely have happened. A mock tool would have exercised
the plumbing and demonstrated nothing about the guarantee.

Use this as the template for a new tool. The shape a tool must have:

1. A factory that takes its configuration and returns a
   :class:`~bacteria.tools.registry.ToolDefinition`, so the same tool can be
   pointed at a temp path in tests and a real one in the CLI. A module-level
   ``ToolDefinition`` with hard-coded paths is not testable without patching.
2. A handler closed over that configuration, taking one dict and returning
   something stringifiable.
3. A description written for the model, not for a maintainer.
4. Its own load-bearing tests, covering what the *handler* does. The registry's
   tests cover registration; only the tool's tests cover its side effect.

The handler returns a confirmation string rather than ``None``. The return value
is fed back to the model as a ``tool_result``, and a model that receives an
empty result frequently assumes failure and retries.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from bacteria.tools.registry import ToolDefinition

DEFAULT_NOTES_PATH = Path(".bacteria/notes.txt")
"""Relative to the working directory, and gitignored. Deliberately inside the
project rather than in a user-wide location: a tool's blast radius should be
visible from where its output lands."""


def build_add_note_tool(notes_path: Path = DEFAULT_NOTES_PATH) -> ToolDefinition:
    """Build an ``add_note`` tool writing to ``notes_path``.

    Args:
        notes_path: Target file. Created along with any missing parent
            directories on first write.

    Returns:
        A registrable tool definition.
    """

    def handler(tool_input: dict[str, Any]) -> str:
        text = tool_input["text"]
        notes_path.parent.mkdir(parents=True, exist_ok=True)
        # Append, never truncate: a tool whose failure mode is "erased the
        # user's notes" is the wrong first tool to hand a model.
        with notes_path.open("a", encoding="utf-8") as f:
            f.write(text + "\n")
        return f"saved note: {text}"

    return ToolDefinition(
        name="add_note",
        description="Appends a short note to a local notes file, for the user to read later.",
        input_schema={
            "type": "object",
            "properties": {"text": {"type": "string", "description": "The note text to save."}},
            "required": ["text"],
        },
        handler=handler,
    )
