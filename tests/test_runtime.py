"""Load-bearing invariant tests for the runtime (Part 4 and Part 6 decisions)."""

import pytest

from bacteria.model.client import ModelResponse
from bacteria.runtime.runtime import Runtime, StepAlreadyExecutedError, StepTracker
from bacteria.session.store import SessionStore
from bacteria.tools.registry import ToolDefinition, ToolRegistry


def test_step_cannot_silently_run_twice():
    """The load-bearing property this part is actually about: a step, once
    executed, refuses to run again within the same run."""
    tracker = StepTracker()
    tracker.run_once("step-1", lambda: "done")

    with pytest.raises(StepAlreadyExecutedError):
        tracker.run_once("step-1", lambda: "done again")


def test_each_turn_gets_a_fresh_run_id(make_fake_model_client):
    store = SessionStore()
    session = store.create_session(user_id="u1")
    client = make_fake_model_client()
    runtime = Runtime(model_client=client, session_store=store)

    result_a = runtime.run_turn(session.session_id, "hello")
    result_b = runtime.run_turn(session.session_id, "again")

    assert result_a.run_id != result_b.run_id


def test_runtime_commits_via_propose_commit_not_direct_write(make_fake_model_client):
    """'Model/runtime output is always a proposal, never a direct write' (Part 3)
    — verified here at the integration level: after a turn, the change is
    visible only through the store's own committed state."""
    store = SessionStore()
    session = store.create_session(user_id="u1")
    client = make_fake_model_client(text="assistant reply")
    runtime = Runtime(model_client=client, session_store=store)

    result = runtime.run_turn(session.session_id, "hello")

    assert len(result.committed_state.transcript) == 2
    assert store.get_state(session.session_id).transcript == result.committed_state.transcript


def test_runtime_calls_model_client_exactly_once_per_turn(make_fake_model_client):
    """The runtime orchestrates the model client; it doesn't retry or
    duplicate the call on its own."""
    store = SessionStore()
    session = store.create_session(user_id="u1")
    client = make_fake_model_client()
    runtime = Runtime(model_client=client, session_store=store)

    runtime.run_turn(session.session_id, "hello")

    assert client.calls == 1


def test_second_turn_sees_prior_transcript(make_fake_model_client):
    """Runtime reads existing transcript state before assembling the next
    turn's messages — session store remains the source of truth."""
    store = SessionStore()
    session = store.create_session(user_id="u1")
    client = make_fake_model_client()
    runtime = Runtime(model_client=client, session_store=store)

    runtime.run_turn(session.session_id, "first")
    runtime.run_turn(session.session_id, "second")

    state = store.get_state(session.session_id)
    assert len(state.transcript) == 4


class FakeToolCallingClient:
    """Returns a tool_use response once, then a plain text response —
    enough to drive one round of Runtime's tool-execution loop."""

    def __init__(self) -> None:
        self.calls = 0

    def send(self, messages, **kwargs) -> ModelResponse:
        self.calls += 1
        if self.calls == 1:
            return ModelResponse(
                text=None,
                tool_calls=[{"id": "t1", "name": "get_time", "input": {}}],
                stop_reason="tool_use",
                raw=None,
            )
        return ModelResponse(text="It's 10:00", tool_calls=[], stop_reason="end_turn", raw=None)


def test_runtime_executes_tool_calls_via_the_execution_module_not_the_model_client():
    """The load-bearing property Part 6 is actually about: a tool call is
    executed by the dedicated execution module, orchestrated by Runtime —
    never by the model client itself, which only ever reports the proposal."""
    store = SessionStore()
    session = store.create_session(user_id="u1")
    client = FakeToolCallingClient()
    runtime = Runtime(model_client=client, session_store=store)

    handler_calls = []
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="get_time",
            description="returns the current time",
            input_schema={"type": "object"},
            handler=lambda tool_input: handler_calls.append(tool_input) or "10:00",
        )
    )

    result = runtime.run_turn(session.session_id, "what time is it?", tool_registry=registry)

    assert len(handler_calls) == 1  # the execution module ran the handler, once
    assert client.calls == 2  # one call proposing the tool, one call after execution
    assert result.response.text == "It's 10:00"


def test_tool_execution_is_recorded_in_the_transcript():
    """Checklist item 7: 'trace the whole path.' A tool call must be visible
    in session state, not disappear between the two model calls — directly
    guards failure mode #7 ('approval hidden in implementation')."""
    store = SessionStore()
    session = store.create_session(user_id="u1")
    client = FakeToolCallingClient()
    runtime = Runtime(model_client=client, session_store=store)

    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="get_time",
            description="returns the current time",
            input_schema={"type": "object"},
            handler=lambda tool_input: "10:00",
        )
    )

    result = runtime.run_turn(session.session_id, "what time is it?", tool_registry=registry)

    tool_items = [item for item in result.committed_state.transcript if item.kind == "tool_call"]
    assert len(tool_items) == 1
    assert tool_items[0].payload == {"name": "get_time", "output": "10:00"}
