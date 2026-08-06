"""Invariant tests for the one place a side effect can happen."""

import pytest

from bacteria.tools.execution import ToolExecutionError, execute_tool_call
from bacteria.tools.registry import ToolDefinition, ToolRegistry


def make_registry(handler=None) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="echo",
            description="echoes input",
            input_schema={"type": "object"},
            handler=handler or (lambda tool_input: tool_input["text"]),
        )
    )
    return registry


def test_unknown_tool_call_is_rejected():
    registry = make_registry()
    with pytest.raises(ToolExecutionError):
        execute_tool_call({"id": "t1", "name": "does-not-exist", "input": {}}, registry)


def test_rejected_approval_prevents_the_handler_from_running():
    """Rejection must mean nothing happened, not that something is regretted.

    A gate checked after the handler runs still reports "rejected" and is
    worthless — the side effect already landed. The assertion that matters is
    the empty ``called`` list, not the raised exception.
    """
    called = []
    registry = make_registry(handler=lambda tool_input: called.append(tool_input))

    with pytest.raises(ToolExecutionError):
        execute_tool_call(
            {"id": "t1", "name": "echo", "input": {"text": "hi"}},
            registry,
            approve=lambda _call: False,
        )

    assert called == []


def test_approved_call_runs_the_handler_and_returns_its_output():
    registry = make_registry()

    result = execute_tool_call({"id": "t1", "name": "echo", "input": {"text": "hi"}}, registry)

    assert result.tool_call_id == "t1"
    assert result.output == "hi"


def test_handler_failure_is_wrapped_not_leaked_raw():
    def boom(_tool_input):
        raise ValueError("handler blew up")

    registry = make_registry(handler=boom)

    with pytest.raises(ToolExecutionError):
        execute_tool_call({"id": "t1", "name": "echo", "input": {"text": "hi"}}, registry)
