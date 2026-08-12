"""Invariant tests for the one place a side effect can happen."""

import threading

import pytest

from bacteria.agent.tools.execution import ToolExecutionError, execute_tool_call
from bacteria.agent.tools.registry import ToolDefinition, ToolRegistry


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


async def test_unknown_tool_call_is_rejected():
    registry = make_registry()
    with pytest.raises(ToolExecutionError):
        await execute_tool_call({"id": "t1", "name": "does-not-exist", "input": {}}, registry)


async def test_rejected_approval_prevents_the_handler_from_running():
    """Rejection must mean nothing happened, not that something is regretted.

    A gate checked after the handler runs still reports "rejected" and is
    worthless — the side effect already landed. The assertion that matters is
    the empty ``called`` list, not the raised exception.
    """
    called = []
    registry = make_registry(handler=lambda tool_input: called.append(tool_input))

    with pytest.raises(ToolExecutionError):
        await execute_tool_call(
            {"id": "t1", "name": "echo", "input": {"text": "hi"}},
            registry,
            approve=lambda _call: False,
        )

    assert called == []


async def test_approved_call_runs_the_handler_and_returns_its_output():
    registry = make_registry()

    result = await execute_tool_call(
        {"id": "t1", "name": "echo", "input": {"text": "hi"}}, registry
    )

    assert result.tool_call_id == "t1"
    assert result.output == "hi"


async def test_handler_failure_is_wrapped_not_leaked_raw():
    def boom(_tool_input):
        raise ValueError("handler blew up")

    registry = make_registry(handler=boom)

    with pytest.raises(ToolExecutionError):
        await execute_tool_call({"id": "t1", "name": "echo", "input": {"text": "hi"}}, registry)


async def test_a_coroutine_handler_is_awaited_not_returned_unrun():
    """An ``async def`` tool must be run, not handed back as a coroutine.

    The silent failure is specific and ugly: a coroutine object satisfies every
    downstream type, so it flows into the transcript and back to the model as
    the string ``<coroutine object ...>``. The tool appears to have succeeded
    and returned nonsense, and the handler never actually ran.
    """

    async def handler(tool_input):
        return tool_input["text"].upper()

    registry = make_registry(handler=handler)

    result = await execute_tool_call(
        {"id": "t1", "name": "echo", "input": {"text": "hi"}}, registry
    )

    assert result.output == "HI"


async def test_a_synchronous_handler_does_not_run_on_the_event_loop_thread():
    """A blocking tool must be threaded off, or it stalls every other turn.

    This is the invariant the whole sync/async split exists to protect, and it
    is invisible without an assertion like this one: calling a synchronous
    handler directly works perfectly in a test and in a single-user CLI, then
    serializes an entire service the first time two requests overlap.
    """
    loop_thread = threading.get_ident()
    handler_thread = []

    registry = make_registry(
        handler=lambda _tool_input: handler_thread.append(threading.get_ident())
    )

    await execute_tool_call({"id": "t1", "name": "echo", "input": {"text": "hi"}}, registry)

    assert handler_thread and handler_thread[0] != loop_thread


async def test_a_coroutine_approval_gate_is_awaited():
    """The gate may be async, because a real one waits on a person.

    A service cannot answer "should this run" from a predicate — it has to
    persist the question and await someone answering it. If a coroutine gate
    were not awaited, the returned coroutine object would be truthy, and every
    call would be approved regardless of the decision.
    """
    called = []

    async def deny(_tool_call):
        return False

    registry = make_registry(handler=lambda tool_input: called.append(tool_input))

    with pytest.raises(ToolExecutionError):
        await execute_tool_call(
            {"id": "t1", "name": "echo", "input": {"text": "hi"}}, registry, approve=deny
        )

    assert called == []
