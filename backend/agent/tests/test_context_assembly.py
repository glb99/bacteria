"""Invariant tests for context assembly: what the model is and is not shown."""

from datetime import datetime, timezone

from bacteria.agent.context.assembly import assemble_context
from bacteria.agent.context.retrieval import RecentMemory, RetrievesMemory, Selection
from bacteria.agent.session.store import MemoryEntry, SessionStore, TranscriptItem


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
    await store.commit(
        session.session_id,
        new_transcript_items=[
            TranscriptItem(kind="message", payload={"role": "user", "text": "hello"})
        ],
    )
    await store.remember(
        session.session_id, key="tone", value="prefers concise answers", reason="user asked once"
    )
    state = await store.get_state(session.session_id)

    context = assemble_context(state, user_text="next")

    assert context.system is not None
    assert "prefers concise answers" in context.system
    assert not any("prefers concise answers" in m["content"] for m in context.messages)


async def test_both_scopes_reach_the_model():
    """A standing fact and this conversation's are both context.

    User-scoped memory that never reached assembly would be storage with no
    reader — the shape the persistence audit kept finding elsewhere in this
    project, and the one that looks like a working feature from the outside.
    """
    store = SessionStore()
    session = await store.create_session(user_id="u1")
    await store.remember(
        session.session_id, key="lang", value="writes in Spanish", reason="r", scope="user"
    )
    await store.remember(session.session_id, key="topic", value="asking about DNS", reason="r")

    context = assemble_context(await store.get_state(session.session_id), user_text="hi")

    assert "writes in Spanish" in context.system
    assert "asking about DNS" in context.system
    assert context.memories_included == 2


async def test_the_session_scope_wins_a_shared_key():
    """One key, one answer. The narrower scope is the more current claim.

    Showing both would hand the model a contradiction and no rule for resolving
    it, which is worse than either value alone.
    """
    store = SessionStore()
    session = await store.create_session(user_id="u1")
    await store.remember(
        session.session_id, key="tone", value="usually verbose", reason="r", scope="user"
    )
    await store.remember(session.session_id, key="tone", value="terse today", reason="r")

    context = assemble_context(await store.get_state(session.session_id), user_text="hi")

    assert "terse today" in context.system
    assert "usually verbose" not in context.system
    assert context.memories_included == 1


async def test_memory_written_in_one_session_is_context_in_another():
    """The claim that makes user scope worth building.

    Within one conversation a memory is largely redundant with the message
    window — the fact is already in the transcript. This asserts the thing the
    window cannot do.
    """
    store = SessionStore()
    first = await store.create_session(user_id="u1")
    second = await store.create_session(user_id="u1")
    await store.remember(
        first.session_id, key="tone", value="prefers terse", reason="asked", scope="user"
    )

    context = assemble_context(await store.get_state(second.session_id), user_text="hi")

    assert context.system is not None
    assert "prefers terse" in context.system


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


async def test_a_dropped_memory_is_counted_rather_than_lost_quietly():
    """A memory the owner kept, which the model was not shown, must be countable.

    This is the failure the strategy seam was extracted to expose. Assembly has
    always dropped the oldest entries past the limit and reported only how many
    it kept, so `memories_in_context: 20` read identically whether twenty
    existed or two hundred did. The owner deliberately preserved every one of
    them and nothing anywhere recorded that most stopped arriving.
    """
    state = await make_state_with_memories(count=50)

    context = assemble_context(state, user_text="hi", memory_limit=10)

    assert context.memories_included == 10
    assert context.memories_considered == 50
    assert context.retrieval_strategy == "recency"


async def test_a_strategy_can_be_substituted_without_touching_assembly():
    """The point of naming the rule: replacing it is a substitution, not an edit.

    Also pins what assembly hands a strategy — one already-collapsed candidate
    set, not two scopes. Precedence is applied before this call so that every
    strategy inherits it rather than re-implementing it, which is how two of
    them would come to disagree.
    """
    seen = {}

    class FirstAlphabetically:
        name = "alphabetical"

        def select(self, query, limit, candidates):
            seen["query"] = query
            seen["candidates"] = dict(candidates)
            chosen = dict(sorted(candidates.items())[:limit])
            return Selection(chosen=chosen, considered=len(candidates), strategy=self.name)

    store = SessionStore()
    session = await store.create_session(user_id="u1")
    await store.remember(session.session_id, key="b", value="beta", reason="r", scope="user")
    await store.remember(session.session_id, key="a", value="alpha", reason="r")

    context = assemble_context(
        await store.get_state(session.session_id),
        user_text="what now?",
        memory_limit=1,
        retriever=FirstAlphabetically(),
    )

    assert isinstance(FirstAlphabetically(), RetrievesMemory)
    assert seen["query"] == "what now?", "the query is handed over even when unused by recency"
    assert set(seen["candidates"]) == {"a", "b"}, "one collapsed set, not per-scope"
    assert "alpha" in context.system and "beta" not in context.system
    assert context.retrieval_strategy == "alphabetical"


async def test_the_default_strategy_still_prefers_the_newest():
    """RecentMemory is a rename, not a rewrite.

    Asserted directly against the strategy rather than through assembly, because
    the ordering subtlety it carries — ascending sort, trimmed from the front,
    so entries sharing a timestamp keep insertion order — is the kind of detail
    a rewrite loses silently.
    """
    older = MemoryEntry(
        value="older", reason="r", created_at=datetime(2020, 1, 1, tzinfo=timezone.utc)
    )
    newer = MemoryEntry(
        value="newer", reason="r", created_at=datetime(2030, 1, 1, tzinfo=timezone.utc)
    )

    selection = RecentMemory().select(query="", limit=1, candidates={"o": older, "n": newer})

    assert list(selection.chosen) == ["n"]
    assert selection.considered == 2
    assert selection.omitted == 1


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
