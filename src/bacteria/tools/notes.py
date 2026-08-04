"""A minimal real local tool — Part 6 (Tools, MCP, and Capability Surfaces).

The first concrete tool registered anywhere in this project. Deliberately
small and low blast-radius (appends a line to a local text file), but with
a real side effect — so it's the first case where the approval boundary
(bacteria.tools.approval) actually gates something instead of confirming a
no-op.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from bacteria.tools.registry import ToolDefinition

DEFAULT_NOTES_PATH = Path(".bacteria/notes.txt")


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
            "properties": {"text": {"type": "string", "description": "The note text to save."}},
            "required": ["text"],
        },
        handler=handler,
    )
