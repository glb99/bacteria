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
