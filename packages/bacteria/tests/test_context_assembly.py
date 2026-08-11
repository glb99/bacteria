"""Invariant tests for context assembly: what the model is and is not shown."""

from bacteria.context.assembly import assemble_context
from bacteria.session.store import SessionStore, TranscriptItem


async def make_state_with_messages(count: int):
    store = SessionStore()
    session = await store.create_session(user_id="u1")
    items = [
        TranscriptItem(kind="message", payload={"role": "user", "text": f"msg-{i}"})
        for i in range(count)
    ]
    await store.commit(session.session_id, new_transcript_items=items)
    return await store.get_state(session.session_id)


async def test_window_caps_transcript_length_to_the_most_recent_messages():
    """Context must not grow with the conversation.

    The failure this prevents is gradual and then sudden: cost and latency
    climb turn over turn, and then one turn overflows the window and the
    conversation stops working entirely.
    """
    state = await make_state_with_messages(count=50)

    context = assemble_context(state, user_text="latest", window_size=10)

    assert len(context.messages) == 11  # 10 windowed + the new user message
    assert context.messages[0]["content"] == "msg-40"  # most recent 10, not oldest
    assert context.messages[-2]["content"] == "msg-49"
    assert context.messages[-1]["content"] == "latest"


async def test_only_messages_become_context_not_the_runs_own_bookkeeping():
    """Evidence about a run must never be fed back to a model as conversation.

    The transcript is an event log, not a script: it holds tool records, run
    errors, and — since ADR 0019 — a `run_meta` item naming the model, the tools
    offered, and how much memory was shown. Replaying those as messages would
    put the system's internals in its own prompt, teach the model the names of
    tools it was not offered this turn, and let an error string become an
    instruction.

    Assembly already filtered by kind; nothing asserted it, and the cost of that
    filter breaking rose sharply the moment run metadata started being recorded.
    """
    store = SessionStore()
    session = await store.create_session(user_id="u1")
    await store.commit(
        session.session_id,
        new_transcript_items=[
            TranscriptItem(kind="message", payload={"role": "user", "text": "real message"}),
            TranscriptItem(
                kind="tool_call",
                payload={"name": "get_time", "input": {}, "status": "executed", "output": "10:00"},
            ),
            TranscriptItem(kind="run_error", payload={"error": "backend unavailable"}),
            TranscriptItem(
                kind="run_meta",
                payload={"model": "secret-model-name", "tools_exposed": ["delete_everything"]},
            ),
        ],
    )
    state = await store.get_state(session.session_id)

    context = assemble_context(state, user_text="next")

    assert [m["content"] for m in context.messages] == ["real message", "next"]
    rendered = str(context.messages) + str(context.system)
    assert "secret-model-name" not in rendered
    assert "delete_everything" not in rendered
    assert "backend unavailable" not in rendered


async def test_no_memory_means_no_system_prompt():
    state = await make_state_with_messages(count=1)

    context = assemble_context(state, user_text="hi")

    assert context.system is None


async def test_memory_is_surfaced_via_system_not_mixed_into_transcript_messages():
    """Memory must stay distinguishable from things that were actually said.

    Appended to the message list, a preserved fact would be indistinguishable
    from a user's utterance this turn — the model would treat what the system
    chose to remember as what someone just told it.
    """
    store = SessionStore()
    session = await store.create_session(user_id="u1")
    await store.commit(session.session_id, new_transcript_items=[
        TranscriptItem(kind="message", payload={"role": "user", "text": "hello"})
    ])
    await store.remember(session.session_id, key="tone", value="prefers concise answers", reason="user asked once")
    state = await store.get_state(session.session_id)

    context = assemble_context(state, user_text="next")

    assert context.system is not None
    assert "prefers concise answers" in context.system
    assert not any("prefers concise answers" in m["content"] for m in context.messages)


async def make_state_with_memories(count: int):
    store = SessionStore()
    session = await store.create_session(user_id="u1")
    for i in range(count):
        await store.remember(session.session_id, key=f"k{i}", value=f"fact-{i}", reason="test")
    return await store.get_state(session.session_id)


async def test_memory_is_bounded_and_keeps_the_most_recent():
    """Memory must not be the one channel that can overflow the window.

    The message window bounds history; without this, memory grew without limit
    in the system prompt and would eventually displace the conversation it was
    meant to inform — through the exact channel the window does not watch.
    """
    state = await make_state_with_memories(count=50)

    context = assemble_context(state, user_text="hi", memory_limit=10)

    kept = [line for line in context.system.splitlines() if line.startswith("- ")]
    assert len(kept) == 10
    assert "fact-49" in context.system
    assert "fact-40" in context.system
    assert "fact-39" not in context.system


async def test_a_zero_window_shows_no_history_rather_than_all_of_it():
    """The strictest bound must not be the loosest one.

    `history[-0:]` is the whole list, so asking for no history returned every
    message — a bound that inverts at its limit is worse than no bound, because
    the caller asked for the safe thing and got the unsafe one.
    """
    state = await make_state_with_messages(count=50)

    context = assemble_context(state, user_text="only me", window_size=0)

    assert [m["content"] for m in context.messages] == ["only me"]


async def test_a_zero_memory_limit_shows_no_memory_rather_than_all_of_it():
    """Same inversion, same reason, on the other bound."""
    state = await make_state_with_memories(count=5)

    context = assemble_context(state, user_text="hi", memory_limit=0)

    assert context.system is None
