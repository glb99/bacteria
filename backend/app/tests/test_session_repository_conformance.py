"""The same behaviours, asserted against both implementations of the protocol.

`SessionRepository` is structural, so a type checker only ever verifies that the
methods exist. Everything that actually matters — reads are detached, commits
append rather than replace, an unknown id raises — is prose in the protocol's
docstring, and an implementation can satisfy every signature while violating all
of it.

So these tests are parameterized over both stores: the agent's in-memory one and
this application's SQL-backed one. A behaviour asserted here is asserted of the
contract, not of a class. If the two ever diverge, the runtime's behaviour would
silently depend on which store it was handed, which is the whole failure the
protocol exists to prevent.
"""

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from bacteria.agent.session.protocol import SessionRepository
from bacteria.agent.session.store import SessionStore, TranscriptItem, UnknownSessionError
from bacteria.app.chat.repository import SqlSessionRepository


@pytest.fixture(params=["in_memory", "sql"], name="repo")
async def _repo(request, engine):
    """One parameter per implementation, so each behaviour is asserted of both.

    The `engine` fixture is requested even for the in-memory case. That costs a
    truncation the in-memory store does not need, and buys a guarantee worth
    more: the two parameters differ only in which store is yielded, so a
    failure on one and not the other is a real divergence rather than a
    difference in how the fixture was set up.
    """
    if request.param == "in_memory":
        yield SessionStore()
        return

    async with AsyncSession(engine) as db:
        yield SqlSessionRepository(db)


def item(text: str, run_id: str | None = None) -> TranscriptItem:
    return TranscriptItem(kind="message", payload={"role": "user", "text": text}, run_id=run_id)


async def test_run_id_survives_storage_and_groups_one_run(repo):
    """The field that makes a run reconstructable has to come back out.

    An in-memory store returns the object it was handed, so it round-trips a
    new field for free and proves nothing. A SQL store rebuilds the item column
    by column, and a `run_id` written but never mapped back — or mapped back but
    never written — reads as `None` on a transcript that otherwise looks
    entirely correct. That is the shape of this failure: not an error, just
    evidence that quietly stops being attributable.

    An item with no run is asserted alongside, because the column is nullable on
    purpose (the agent's ADR 0018) and "belongs to no run" has to survive storage
    too, rather than being flattened into some default.
    """
    session = await repo.create_session(user_id="u1")

    await repo.commit(
        session.session_id,
        new_transcript_items=[item("ask", run_id="run-a"), item("answer", run_id="run-a")],
    )
    await repo.commit(session.session_id, new_transcript_items=[item("orphan")])

    transcript = (await repo.get_state(session.session_id)).transcript
    assert [i.run_id for i in transcript] == ["run-a", "run-a", None]


async def test_satisfies_the_protocol(repo):
    assert isinstance(repo, SessionRepository)


async def test_reads_are_detached_from_the_stored_state(repo):
    """Mutating what you read must change nothing.

    This is the guarantee that makes "only this layer writes" structural rather
    than a rule every caller has to remember. A SQL implementation breaks it by
    returning ORM rows, which are live handles on the database — the mutation
    then lands on the next flush, from code that never meant to write.
    """
    session = await repo.create_session(user_id="u1")

    state = await repo.get_state(session.session_id)
    state.working_state["hacked"] = True
    state.transcript.append(item("sneaky"))

    fresh = await repo.get_state(session.session_id)
    assert fresh.working_state == {}
    assert fresh.transcript == []


async def test_commit_appends_transcript_and_merges_working_state(repo):
    """Neither replaces what is already there.

    A store that replaced the transcript would lose the conversation on every
    turn, and one that replaced working state would drop keys written by an
    earlier step of the same run.
    """
    session = await repo.create_session(user_id="u1")

    await repo.commit(
        session.session_id, new_transcript_items=[item("first")], working_state_updates={"a": 1}
    )
    await repo.commit(
        session.session_id, new_transcript_items=[item("second")], working_state_updates={"b": 2}
    )

    state = await repo.get_state(session.session_id)
    assert [i.payload["text"] for i in state.transcript] == ["first", "second"]
    assert state.working_state == {"a": 1, "b": 2}


async def test_transcript_order_is_the_order_committed(repo):
    """Ordering must survive storage, including within a single commit.

    Two items committed together can share a timestamp to the microsecond, so a
    store ordering by time can return them either way round — and a transcript
    in the wrong order is a conversation that reads as though the model answered
    before it was asked.
    """
    session = await repo.create_session(user_id="u1")
    await repo.commit(session.session_id, new_transcript_items=[item("a"), item("b"), item("c")])
    await repo.commit(session.session_id, new_transcript_items=[item("d")])

    state = await repo.get_state(session.session_id)
    assert [i.payload["text"] for i in state.transcript] == ["a", "b", "c", "d"]


async def test_user_memory_is_shared_across_that_persons_sessions(repo):
    """The whole point of the scope, and the thing session memory cannot do.

    Written first among these because an implementation can satisfy every
    signature in the protocol while storing user memory per session — which is
    session memory with a longer name, and would pass any test that only ever
    looked at one conversation.
    """
    first = await repo.create_session(user_id="u1")
    second = await repo.create_session(user_id="u1")

    await repo.remember(first.session_id, key="tone", value="terse", reason="asked", scope="user")

    state = await repo.get_state(second.session_id)
    assert state.user_memory["tone"].value == "terse"
    assert state.memory == {}, "a user-scoped write must not land in session memory"


async def test_one_persons_memory_is_never_visible_to_another(repo):
    """The leakage boundary. Personalization becomes a breach without it.

    User memory is the first thing here selected by something other than
    `session_id`, so it is the first place a wrong predicate shows one person
    another's data rather than merely the wrong conversation.
    """
    mine = await repo.create_session(user_id="u1")
    theirs = await repo.create_session(user_id="u2")

    await repo.remember(mine.session_id, key="secret", value="mine alone", reason="r", scope="user")

    assert (await repo.get_state(theirs.session_id)).user_memory == {}


async def test_the_two_scopes_are_separate_collections(repo):
    """One key may hold a standing fact and a different one for this conversation.

    They must both survive storage. A store that let one overwrite the other
    would silently destroy a memory the owner had deliberately kept, and
    assembly's precedence rule would have nothing left to resolve.
    """
    session = await repo.create_session(user_id="u1")

    await repo.remember(session.session_id, key="tone", value="standing", reason="r", scope="user")
    await repo.remember(session.session_id, key="tone", value="this one", reason="r")

    state = await repo.get_state(session.session_id)
    assert state.user_memory["tone"].value == "standing"
    assert state.memory["tone"].value == "this one"


async def test_forgetting_one_scope_leaves_the_other(repo):
    """Dropping an override must not delete what it was overriding.

    Those are different intentions and one call cannot mean both — a session
    that stops overriding a standing preference wants the standing one back,
    not gone.
    """
    session = await repo.create_session(user_id="u1")
    await repo.remember(session.session_id, key="tone", value="standing", reason="r", scope="user")
    await repo.remember(session.session_id, key="tone", value="this one", reason="r")

    await repo.forget(session.session_id, key="tone")

    state = await repo.get_state(session.session_id)
    assert state.memory == {}
    assert state.user_memory["tone"].value == "standing"


async def test_a_proposal_can_be_activated_into_user_scope(repo):
    """The human picks the scope at activation; the proposer never does.

    A model able to mark its own suggestion user-scoped would be deciding that
    something it wrote applies to every future conversation that person has.
    """
    first = await repo.create_session(user_id="u1")
    second = await repo.create_session(user_id="u1")
    await repo.propose(first.session_id, key="tone", value="terse", reason="r", source="model")

    await repo.activate(first.session_id, source="model", key="tone", scope="user")

    elsewhere = await repo.get_state(second.session_id)
    assert elsewhere.user_memory["tone"].value == "terse"
    assert elsewhere.user_memory["tone"].source == "model"
    assert (await repo.get_state(first.session_id)).memory == {}


async def test_transcript_and_working_state_do_not_disturb_each_other(repo):
    session = await repo.create_session(user_id="u1")

    await repo.commit(session.session_id, working_state_updates={"a": 1})
    assert (await repo.get_state(session.session_id)).transcript == []

    await repo.commit(session.session_id, new_transcript_items=[item("hi")])
    state = await repo.get_state(session.session_id)
    assert state.working_state == {"a": 1}
    assert len(state.transcript) == 1


async def test_memory_is_written_by_its_own_path_not_by_commit(repo):
    """Working state must not be able to reach memory.

    If it could, "stash this for the current turn" and "keep this permanently"
    would be the same operation, and the difference between them is the entire
    reason memory exists separately.
    """
    session = await repo.create_session(user_id="u1")

    await repo.commit(session.session_id, working_state_updates={"scratch": 1})
    assert (await repo.get_state(session.session_id)).memory == {}

    await repo.remember(session.session_id, key="pref", value="concise", reason="user said so")
    state = await repo.get_state(session.session_id)
    assert state.working_state == {"scratch": 1}
    assert state.memory["pref"].value == "concise"
    assert state.memory["pref"].reason == "user said so"


async def test_remembering_the_same_key_overwrites_rather_than_appends(repo):
    session = await repo.create_session(user_id="u1")

    await repo.remember(session.session_id, key="pref", value="concise", reason="first")
    await repo.remember(session.session_id, key="pref", value="verbose", reason="changed")

    memory = (await repo.get_state(session.session_id)).memory
    assert len(memory) == 1
    assert memory["pref"].value == "verbose"
    assert memory["pref"].reason == "changed"


async def test_overwriting_a_memory_refreshes_its_timestamp(repo):
    """Rewriting a memory makes it recent again, in every implementation.

    Assembly shows the model the most recent entries by ``created_at``, so a
    store that preserved the original timestamp would let a memory the owner
    just rewrote age out of the model's view and stay invisible — while a store
    that refreshed it behaved correctly. The runtime's behaviour would then
    depend on which store it was handed, which is the whole failure this suite
    exists to prevent.

    Found by writing the same key twice against a live server and noticing the
    timestamp had not moved; the in-memory store had been refreshing it all
    along, because ``remember`` builds a whole new entry.
    """
    session = await repo.create_session(user_id="u1")
    await repo.remember(session.session_id, key="pref", value="concise", reason="first")
    first = (await repo.get_state(session.session_id)).memory["pref"].created_at

    await repo.remember(session.session_id, key="pref", value="verbose", reason="changed")
    second = (await repo.get_state(session.session_id)).memory["pref"].created_at

    assert second > first


async def test_forget_removes_and_forgetting_an_absent_key_is_a_no_op(repo):
    session = await repo.create_session(user_id="u1")
    await repo.remember(session.session_id, key="pref", value="concise", reason="r")

    await repo.forget(session.session_id, key="pref")
    await repo.forget(session.session_id, key="never-existed")

    assert (await repo.get_state(session.session_id)).memory == {}


async def test_an_unknown_session_raises_rather_than_being_created(repo):
    """A store that conjures the session turns a lost id into silent data loss.

    Same exception type from both implementations, so a caller that handles one
    handles the other — otherwise the runtime's behaviour depends on which store
    it was given.
    """
    with pytest.raises(UnknownSessionError):
        await repo.get_state("does-not-exist")

    with pytest.raises(UnknownSessionError):
        await repo.commit("does-not-exist", new_transcript_items=[item("x")])


async def test_session_identity_is_independent_of_user_identity(repo):
    a = await repo.create_session(user_id="u1")
    b = await repo.create_session(user_id="u1")

    assert a.session_id != b.session_id
    assert a.user_id == b.user_id == "u1"


async def test_a_proposal_is_kept_apart_from_active_memory(repo):
    """Proposing must not be a way of remembering.

    The security argument of ADR 0017 is exactly this line: a proposal reaches
    no model. An implementation that filed suggestions into `memory` would
    satisfy every signature and hand an injected instruction straight to the
    next turn.
    """
    session = await repo.create_session(user_id="u1")

    await repo.propose(session.session_id, key="tone", value="v", reason="r", source="model")

    state = await repo.get_state(session.session_id)
    assert state.memory == {}
    assert state.proposals[("model", "tone")].value == "v"


async def test_two_sources_may_propose_the_same_key(repo):
    """Proposals are keyed by (source, key), so neither proposer silently wins.

    Last-write-wins would make the survivor depend on when a background job
    happened to run — a timing-dependent, silent outcome, which is the failure
    this project has already had to fix once in transcript ordering.
    """
    session = await repo.create_session(user_id="u1")

    await repo.propose(session.session_id, key="tone", value="a", reason="r", source="model")
    await repo.propose(session.session_id, key="tone", value="b", reason="r", source="job")

    proposals = (await repo.get_state(session.session_id)).proposals
    assert proposals[("model", "tone")].value == "a"
    assert proposals[("job", "tone")].value == "b"


async def test_re_proposing_the_same_source_and_key_replaces(repo):
    """What makes a retried background job safe rather than accumulative."""
    session = await repo.create_session(user_id="u1")

    await repo.propose(session.session_id, key="tone", value="first", reason="r", source="job")
    await repo.propose(session.session_id, key="tone", value="second", reason="r", source="job")

    proposals = (await repo.get_state(session.session_id)).proposals
    assert len(proposals) == 1
    assert proposals[("job", "tone")].value == "second"


async def test_activation_moves_a_proposal_and_keeps_its_source(repo):
    """Provenance survives activation, and the proposal stops being pending.

    A memory that forgot it came from a job cannot later be distrusted as one,
    and a proposal left in the queue after acceptance asks the reviewer the
    same question forever.
    """
    session = await repo.create_session(user_id="u1")
    await repo.propose(session.session_id, key="tone", value="v", reason="r", source="job")

    await repo.activate(session.session_id, source="job", key="tone")

    state = await repo.get_state(session.session_id)
    assert state.memory["tone"].source == "job"
    assert state.proposals == {}


async def test_activation_refreshes_the_timestamp(repo):
    """An accepted memory is recent, whenever it was suggested.

    Assembly shows the model the most recent entries by `created_at`, so
    carrying the proposal's timestamp across would let a suggestion made weeks
    ago be accepted today and immediately be at risk of ageing out — invisible,
    and impossible to explain.

    Written because the two implementations disagreed here: the in-memory store
    moved the entry object across, keeping its timestamp, while the SQL store
    set a new one. Both satisfied the protocol.
    """
    session = await repo.create_session(user_id="u1")
    await repo.propose(session.session_id, key="tone", value="v", reason="r", source="job")
    proposed_at = (await repo.get_state(session.session_id)).proposals[("job", "tone")].created_at

    await repo.activate(session.session_id, source="job", key="tone")

    assert (await repo.get_state(session.session_id)).memory["tone"].created_at > proposed_at


async def test_activation_replaces_whatever_held_the_key(repo):
    """Active memory is keyed by `key` alone, so competing suggestions collapse.

    Two proposals may coexist; two active memories for one key cannot, or the
    model is handed both and told nothing about which is current.
    """
    session = await repo.create_session(user_id="u1")
    await repo.remember(session.session_id, key="tone", value="old", reason="r")
    await repo.propose(session.session_id, key="tone", value="new", reason="r", source="job")

    await repo.activate(session.session_id, source="job", key="tone")

    memory = (await repo.get_state(session.session_id)).memory
    assert len(memory) == 1
    assert memory["tone"].value == "new"


async def test_activating_a_proposal_that_does_not_exist_raises(repo):
    """A stale review page must not conjure a memory nobody just read."""
    session = await repo.create_session(user_id="u1")

    with pytest.raises(KeyError):
        await repo.activate(session.session_id, source="job", key="never-proposed")


async def test_rejecting_removes_a_proposal_and_is_a_no_op_when_absent(repo):
    session = await repo.create_session(user_id="u1")
    await repo.propose(session.session_id, key="tone", value="v", reason="r", source="job")

    await repo.reject(session.session_id, source="job", key="tone")
    await repo.reject(session.session_id, source="job", key="never-proposed")

    state = await repo.get_state(session.session_id)
    assert state.proposals == {}
    assert state.memory == {}
