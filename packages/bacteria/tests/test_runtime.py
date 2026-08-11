"""Invariant tests for the runtime: ordering, delegation, and what survives failure.

The runtime is where the layers meet, so these are mostly integration tests —
they assert that a turn *delegates* correctly, not that any one layer works.
"""

import pytest
from bacteria.model.protocol import ModelResponse
from bacteria.runtime.runtime import Runtime, StepAlreadyExecutedError, StepTracker
from bacteria.session.store import SessionStore
from bacteria.tools.execution import ToolExecutionError
from bacteria.tools.registry import ToolDefinition, ToolRegistry


async def test_step_cannot_silently_run_twice():
    """A step, once executed, refuses to run again within the same run.

    Guards the expensive bug class here: control flow looping back over a step
    whose side effect already landed.
    """

    async def step() -> str:
        return "done"

    tracker = StepTracker()
    await tracker.run_once("step-1", step)

    with pytest.raises(StepAlreadyExecutedError):
        await tracker.run_once("step-1", step)


async def test_each_turn_gets_a_fresh_run_id(make_fake_model_client):
    store = SessionStore()
    session = await store.create_session(user_id="u1")
    client = make_fake_model_client()
    runtime = Runtime(model_client=client, session_store=store)

    result_a = await runtime.run_turn(session.session_id, "hello")
    result_b = await runtime.run_turn(session.session_id, "again")

    assert result_a.run_id != result_b.run_id


async def test_runtime_commits_via_the_store_not_by_direct_write(make_fake_model_client):
    """The runtime proposes; only the store writes.

    Checked at the integration level: after a turn, the change is visible
    through the store's own state, which is only possible if it went through
    commit().
    """
    store = SessionStore()
    session = await store.create_session(user_id="u1")
    client = make_fake_model_client(text="assistant reply")
    runtime = Runtime(model_client=client, session_store=store)

    result = await runtime.run_turn(session.session_id, "hello")

    # Counted by kind rather than by length: a run also commits evidence about
    # itself, and this test is about the conversation reaching the store.
    messages = [i for i in result.committed_state.transcript if i.kind == "message"]
    assert len(messages) == 2
    assert (
        await store.get_state(session.session_id)
    ).transcript == result.committed_state.transcript


async def test_runtime_calls_model_client_exactly_once_per_turn(make_fake_model_client):
    """The runtime does not retry or duplicate the model call.

    Retry lives in the model client, where the request is known to be
    side-effect free. A second retry layer here would multiply attempts.
    """
    store = SessionStore()
    session = await store.create_session(user_id="u1")
    client = make_fake_model_client()
    runtime = Runtime(model_client=client, session_store=store)

    await runtime.run_turn(session.session_id, "hello")

    assert client.calls == 1


async def test_second_turn_sees_prior_transcript(make_fake_model_client):
    """History comes from the store, not from anything the runtime kept.

    The runtime holds no state between turns; a second turn sees the first only
    because it re-reads the source of truth.
    """
    store = SessionStore()
    session = await store.create_session(user_id="u1")
    client = make_fake_model_client()
    runtime = Runtime(model_client=client, session_store=store)

    await runtime.run_turn(session.session_id, "first")
    await runtime.run_turn(session.session_id, "second")

    state = await store.get_state(session.session_id)
    assert len([i for i in state.transcript if i.kind == "message"]) == 4


class FakeToolCallingClient:
    """Returns a tool_use response once, then a plain text response —
    enough to drive one round of Runtime's tool-execution loop."""

    def __init__(self) -> None:
        self.calls = 0

    async def send(self, messages, **kwargs) -> ModelResponse:
        self.calls += 1
        if self.calls == 1:
            return ModelResponse(
                text=None,
                tool_calls=[{"id": "t1", "name": "get_time", "input": {}}],
                stop_reason="tool_use",
                raw=None,
                model="fake-model-1",
            )
        return ModelResponse(
            text="It's 10:00",
            tool_calls=[],
            stop_reason="end_turn",
            raw=None,
            model="fake-model-1",
        )


async def test_runtime_executes_tool_calls_via_the_execution_module_not_the_model_client():
    """A proposal becomes an action only by passing through the execution module.

    The model client reports; the runtime sequences; execution runs. This
    asserts all three at once — the handler ran exactly once, and the model was
    called twice, meaning the second call carried real results rather than the
    model having somehow acted for itself.
    """
    store = SessionStore()
    session = await store.create_session(user_id="u1")
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

    result = await runtime.run_turn(session.session_id, "what time is it?", tool_registry=registry)

    assert len(handler_calls) == 1  # the execution module ran the handler, once
    assert client.calls == 2  # one call proposing the tool, one call after execution
    assert result.response.text == "It's 10:00"


async def test_tool_execution_is_recorded_in_the_transcript():
    """A tool call must be visible in session state, not only in the model exchange.

    Without this, what ran and what it returned exists only inside a callback
    and between two API calls — so the one durable record of the conversation
    would show an assistant answer with no account of where it came from.
    """
    store = SessionStore()
    session = await store.create_session(user_id="u1")
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

    result = await runtime.run_turn(session.session_id, "what time is it?", tool_registry=registry)

    tool_items = [item for item in result.committed_state.transcript if item.kind == "tool_call"]
    assert len(tool_items) == 1
    assert tool_items[0].payload == {
        "name": "get_time",
        "input": {},
        "status": "executed",
        "output": "10:00",
    }


def make_get_time_registry(handler=None) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="get_time",
            description="returns the current time",
            input_schema={"type": "object"},
            handler=handler or (lambda tool_input: "10:00"),
        )
    )
    return registry


async def test_runtime_honors_a_rejecting_approval_callback():
    """A rejected call does not run, and the rejection is not swallowed.

    Both halves matter. Running it anyway defeats the gate; catching the
    rejection and continuing quietly leaves the user believing they stopped
    something they did not.
    """
    store = SessionStore()
    session = await store.create_session(user_id="u1")
    client = FakeToolCallingClient()
    runtime = Runtime(model_client=client, session_store=store)

    handler_calls = []
    registry = make_get_time_registry(handler=lambda tool_input: handler_calls.append(tool_input))

    with pytest.raises(ToolExecutionError):
        await runtime.run_turn(
            session.session_id,
            "what time is it?",
            tool_registry=registry,
            approve=lambda _tool_call: False,
        )

    assert handler_calls == []


async def test_a_rejected_tool_call_still_leaves_evidence_in_the_transcript():
    """A failed run still commits enough evidence to explain itself.

    The exception carries the failure to the caller and then it is gone. What
    remains has to be in the transcript: the user's message, the attempt, and
    why it stopped.
    """
    store = SessionStore()
    session = await store.create_session(user_id="u1")
    client = FakeToolCallingClient()
    runtime = Runtime(model_client=client, session_store=store)

    registry = make_get_time_registry()

    with pytest.raises(ToolExecutionError):
        await runtime.run_turn(
            session.session_id,
            "what time is it?",
            tool_registry=registry,
            approve=lambda _tool_call: False,
        )

    transcript = (await store.get_state(session.session_id)).transcript
    assert transcript[0].payload == {"role": "user", "text": "what time is it?"}
    tool_items = [item for item in transcript if item.kind == "tool_call"]
    assert tool_items[0].payload["status"] == "failed"
    assert tool_items[0].payload["name"] == "get_time"
    assert any(item.kind == "run_error" for item in transcript)


class FakeFailingClient:
    """Fails on the first model call, before any tool is involved.

    Covers the other route into the failure path: not a rejected tool, but the
    model call itself. This is the case that loses the user's own message if
    evidence is not committed.
    """

    async def send(self, messages, **kwargs) -> ModelResponse:
        raise RuntimeError("model backend unavailable")


async def test_a_failed_model_call_still_leaves_the_user_message_as_evidence():
    store = SessionStore()
    session = await store.create_session(user_id="u1")
    runtime = Runtime(model_client=FakeFailingClient(), session_store=store)

    with pytest.raises(RuntimeError):
        await runtime.run_turn(session.session_id, "hello")

    transcript = (await store.get_state(session.session_id)).transcript
    assert transcript[0].payload == {"role": "user", "text": "hello"}
    assert any(item.kind == "run_error" for item in transcript)


async def test_every_item_a_run_commits_carries_that_run_id():
    """No item a turn writes may be left unattributed.

    `TranscriptItem.run_id` is optional, so a construction site that forgets it
    produces a perfectly valid item that simply belongs to no run — no type
    error, no failed write, nothing to notice until someone needs the evidence.
    This is the check that makes forgetting loud. It drives a turn through the
    tool path deliberately, because that is where the items are built somewhere
    other than `run_turn` itself.
    """
    store = SessionStore()
    session = await store.create_session(user_id="u1")
    runtime = Runtime(model_client=FakeToolCallingClient(), session_store=store)

    result = await runtime.run_turn(
        session.session_id, "what time is it?", tool_registry=make_get_time_registry()
    )

    transcript = (await store.get_state(session.session_id)).transcript
    assert {item.kind for item in transcript} == {"message", "tool_call", "run_meta"}
    assert [item.run_id for item in transcript] == [result.run_id] * len(transcript)


async def test_a_failed_run_is_separable_from_the_retry_that_followed_it(make_fake_model_client):
    """Two attempts at one message are two runs, not one stuttering conversation.

    This is what the id is for. A failed turn commits its evidence and re-raises
    (ADR 0012), the caller retries, and both attempts land in the same session
    in order. Without `run_id` the abandoned attempt can only be guessed at from
    a `run_error` sitting next to a repeated question — and that guess gets
    harder as soon as a retry also fails.
    """
    store = SessionStore()
    session = await store.create_session(user_id="u1")

    failing = Runtime(model_client=FakeFailingClient(), session_store=store)
    with pytest.raises(RuntimeError):
        await failing.run_turn(session.session_id, "hello")

    succeeding = Runtime(model_client=make_fake_model_client(), session_store=store)
    retry = await succeeding.run_turn(session.session_id, "hello")

    transcript = (await store.get_state(session.session_id)).transcript
    runs = {item.run_id for item in transcript}
    assert len(runs) == 2
    assert None not in runs

    abandoned = next(run for run in runs if run != retry.run_id)
    failed_items = [item for item in transcript if item.run_id == abandoned]
    assert [item.kind for item in failed_items] == ["message", "run_error", "run_meta"]
    assert failed_items[-1].payload["outcome"] == "failed"


async def test_a_run_records_how_it_was_configured():
    """Two runs with identical text may have been given entirely different runs.

    This is the record that tells them apart: which model answered, what it was
    shown, and what it was allowed to do. Without it a transcript is readable
    and not reconstructable — and an evaluation asking "did this run use the
    right tool, with the right model" has nothing to read.
    """
    store = SessionStore()
    session = await store.create_session(user_id="u1")
    await store.remember(session.session_id, key="tone", value="terse", reason="asked")
    runtime = Runtime(model_client=FakeToolCallingClient(), session_store=store)

    await runtime.run_turn(
        session.session_id, "what time is it?", tool_registry=make_get_time_registry()
    )

    transcript = (await store.get_state(session.session_id)).transcript
    metas = [item for item in transcript if item.kind == "run_meta"]
    assert len(metas) == 1, "exactly one per run, or a run has two descriptions"
    assert metas[0].payload == {
        "model": "fake-model-1",
        "tools_exposed": ["get_time"],
        "messages_in_context": 1,
        "memories_in_context": 1,
        "memories_considered": 1,
        "retrieval_strategy": "recency",
        "tool_calls_proposed": 1,
        "tool_calls_dropped": 0,
        "outcome": "completed",
    }


async def test_a_run_that_fails_before_the_model_answers_still_describes_itself():
    """The runs most worth explaining are the ones that produced no answer.

    A run pointed at an unreachable model records no model, and that null is
    the finding rather than a gap — it says the failure happened before
    anything replied. Asserted because the natural implementation builds this
    record from the response, which on this path does not exist.
    """
    store = SessionStore()
    session = await store.create_session(user_id="u1")
    runtime = Runtime(model_client=FakeFailingClient(), session_store=store)

    with pytest.raises(RuntimeError):
        await runtime.run_turn(session.session_id, "hello")

    transcript = (await store.get_state(session.session_id)).transcript
    meta = next(item for item in transcript if item.kind == "run_meta")
    assert meta.payload["outcome"] == "failed"
    assert meta.payload["model"] is None
    assert meta.payload["tool_calls_proposed"] == 0


async def test_a_refused_tool_call_is_distinguishable_from_one_that_broke():
    """ "The boundary held" and "the tool crashed" must not look the same.

    Both stop the run with a `ToolExecutionError` and both record `status:
    failed`, so control flow genuinely cannot tell them apart — but they are
    opposite facts about the system. Recovering the difference by matching on
    the error message would make stored evidence depend on error wording.
    """

    async def run_and_capture(registry, approve):
        store = SessionStore()
        session = await store.create_session(user_id="u1")
        runtime = Runtime(model_client=FakeToolCallingClient(), session_store=store)
        with pytest.raises(ToolExecutionError):
            await runtime.run_turn(
                session.session_id, "go", tool_registry=registry, approve=approve
            )
        transcript = (await store.get_state(session.session_id)).transcript
        return next(i for i in transcript if i.kind == "tool_call").payload

    def explode(_tool_input):
        raise RuntimeError("the handler broke")

    refused = await run_and_capture(make_get_time_registry(), lambda _c: False)
    broke = await run_and_capture(make_get_time_registry(handler=explode), lambda _c: True)

    assert refused["status"] == broke["status"] == "failed"
    assert refused["reason"] == "rejected"
    assert broke["reason"] == "handler_error"


async def test_runtime_honors_an_approving_callback():
    store = SessionStore()
    session = await store.create_session(user_id="u1")
    client = FakeToolCallingClient()
    runtime = Runtime(model_client=client, session_store=store)

    registry = make_get_time_registry()

    result = await runtime.run_turn(
        session.session_id,
        "what time is it?",
        tool_registry=registry,
        approve=lambda _tool_call: True,
    )

    assert result.response.text == "It's 10:00"
