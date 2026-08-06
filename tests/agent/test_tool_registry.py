"""Invariant tests for the capability surface: what the model gets told about."""

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
    """Nothing capable of running code may reach the model.

    Asserted as an exact key set rather than an absence check, so that a field
    added to ToolDefinition later fails here instead of silently shipping.
    """
    registry = ToolRegistry()
    registry.register(make_tool())

    schema = registry.schemas_for_run()[0]

    assert set(schema.keys()) == {"name", "description", "input_schema"}


def test_schemas_for_run_filters_to_the_allowed_list():
    """A run can be given fewer tools than the registry holds.

    Everything a model can see, it will eventually try — so narrowing has to
    actually narrow.
    """
    registry = ToolRegistry()
    registry.register(make_tool("echo"))
    registry.register(make_tool("delete_file"))

    schemas = registry.schemas_for_run(allowed=["echo"])

    assert [s["name"] for s in schemas] == ["echo"]


def test_unregistered_tool_is_rejected():
    registry = ToolRegistry()
    with pytest.raises(UnknownToolError):
        registry.get("does-not-exist")
