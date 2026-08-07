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
from bacteria.session.protocol import SessionRepository
from bacteria.session.store import SessionStore, TranscriptItem, UnknownSessionError
from sqlmodel.ext.asyncio.session import AsyncSession

from fastpaip.chat.repository import SqlSessionRepository


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


def item(text: str) -> TranscriptItem:
    return TranscriptItem(kind="message", payload={"role": "user", "text": text})


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

    await repo.commit(session.session_id, new_transcript_items=[item("first")], working_state_updates={"a": 1})
    await repo.commit(session.session_id, new_transcript_items=[item("second")], working_state_updates={"b": 2})

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
