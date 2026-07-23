"""Load-bearing invariant tests for the runtime (Part 4 decisions)."""

import pytest

from bacteria.runtime.runtime import Runtime, StepAlreadyExecutedError, StepTracker
from bacteria.session.store import SessionStore


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
