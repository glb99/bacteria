"""Load-bearing invariant tests for the tool registry (Part 6 decisions)."""

import pytest

from bacteria.tools.registry import ToolDefinition, ToolRegistry, UnknownToolError


def make_tool(name="echo") -> ToolDefinition:
    return ToolDefinition(
        name=name,
        description="echoes input",
        input_schema={"type": "object", "properties": {"text": {"type": "string"}}},
        handler=lambda tool_input: tool_input["text"],
    )


def test_schema_never_exposes_the_handler():
    """'The model only ever sees name/description/input_schema' — the schema
    sent to the model must never carry anything capable of running code."""
    registry = ToolRegistry()
    registry.register(make_tool())

    schema = registry.schemas_for_run()[0]

    assert set(schema.keys()) == {"name", "description", "input_schema"}


def test_schemas_for_run_filters_to_the_allowed_list():
    """Checklist item 1: 'expose only tools needed for this run,' not the
    whole registry by default when a caller narrows it."""
    registry = ToolRegistry()
    registry.register(make_tool("echo"))
    registry.register(make_tool("delete_file"))

    schemas = registry.schemas_for_run(allowed=["echo"])

    assert [s["name"] for s in schemas] == ["echo"]


def test_unregistered_tool_is_rejected():
    registry = ToolRegistry()
    with pytest.raises(UnknownToolError):
        registry.get("does-not-exist")
