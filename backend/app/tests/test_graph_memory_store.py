"""The graph as keyed memory, and the guarantee that had to be restated.

Two stores now answer the same questions. What matters is not that this one
works but that it agrees with the other where it should, and differs visibly
where it must — ADR 0010 exists to make that difference observable rather than
argued about.

Real Postgres, like everything that touches storage here.
"""

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from bacteria.agent.session.store import USER_SCOPE
from bacteria.app.chat.graph_memory import GraphMemoryStore, UnknownPreferenceError
from bacteria.app.chat.repository import SqlSessionRepository

USER = "graph-memory"


@pytest.fixture(name="store")
async def _store(engine):
    async with AsyncSession(engine) as db:
        session = await SqlSessionRepository(db).create_session(USER)
        yield GraphMemoryStore(db), session.session_id


async def test_a_stated_preference_round_trips(store):
    """`remember` then `entries` — the contract every store owes."""
    memory, session_id = store
    await memory.remember(session_id, USER, "tone", "concise", "they said so")

    view = await memory.entries(session_id, USER)

    assert view.memory["tone"].value == "concise"
    assert view.memory["tone"].reason == "they said so"


async def test_a_proposal_does_not_reach_the_speakable_collections(store):
    """ADR 0010 §5's guarantee, which moved from two tables to one column.

    The table store makes "reaches the model" a question of which table a row is
    in — something you cannot forget. One log holding both cannot have that, so
    the filter lives in one function and this is the test that stands in for the
    structure that was lost.
    """
    memory, session_id = store
    await memory.propose(session_id, "tone", "terse", "guessed from the transcript", source="x")

    view = await memory.entries(session_id, USER)

    assert view.memory == {}
    assert view.user_memory == {}
    assert view.proposals != {}, "it is held, and it is not speakable"


async def test_activating_states_what_was_proposed(store):
    """Ratification appends rather than moving: both rows survive, differing in origin."""
    memory, session_id = store
    await memory.propose(session_id, "tone", "terse", "guessed", source="extractor")

    await memory.activate(session_id, USER, "extractor", "tone")

    view = await memory.entries(session_id, USER)
    assert view.memory["tone"].value == "terse", "now speakable"
    assert view.proposals != {}, "and the proposal it came from is still recorded"


async def test_activating_nothing_is_refused(store):
    """Matching the table store rather than conjuring a memory from nothing."""
    memory, session_id = store

    with pytest.raises(KeyError):
        await memory.activate(session_id, USER, "extractor", "tone")


async def test_user_scope_and_session_scope_land_in_different_collections(store):
    memory, session_id = store
    await memory.remember(session_id, USER, "tone", "concise", "said so")
    await memory.remember(session_id, USER, "language", "spanish", "said so", scope=USER_SCOPE)

    view = await memory.entries(session_id, USER)

    assert "tone" in view.memory
    assert "language" in view.user_memory


async def test_forgetting_removes_it_from_what_may_be_spoken(store):
    memory, session_id = store
    await memory.remember(session_id, USER, "tone", "concise", "said so")

    await memory.forget(session_id, USER, "tone")

    assert (await memory.entries(session_id, USER)).memory == {}


async def test_rejecting_removes_the_proposal(store):
    memory, session_id = store
    await memory.propose(session_id, "tone", "terse", "guessed", source="extractor")

    await memory.reject(session_id, "extractor", "tone")

    assert (await memory.entries(session_id, USER)).proposals == {}


async def test_a_key_the_catalogue_does_not_know_is_refused(store):
    """**The substantive difference between the two stores**, surfaced not hidden.

    A table takes any key. The graph takes the ones its vocabulary knows, because
    a claim under an unratified relation cannot be projected — no relation, no
    key, nothing to return. Accepting it would make `remember` report success and
    lose the fact, which is worse than a refusal a caller can see.
    """
    memory, session_id = store

    with pytest.raises(UnknownPreferenceError):
        await memory.remember(session_id, USER, "favourite_biscuit", "rich tea", "said so")


async def test_it_starts_empty(store):
    """Nothing extracts a preference yet, so this is the honest initial state.

    Recorded as a test because it is the first thing a comparison against the
    tables will show, and it should read as a known gap rather than a failure.
    """
    memory, session_id = store

    view = await memory.entries(session_id, USER)

    assert (view.memory, view.user_memory, view.proposals) == ({}, {}, {})


async def test_what_the_extractor_heard_arrives_as_a_proposal(engine):
    """The two halves meeting: extraction writes, the store reads, nothing speaks.

    Until this, `GraphMemoryStore` had no way to be non-empty except by somebody
    calling `remember` — so the comparison against the tables could only ever
    report that the graph knew nothing.
    """
    from datetime import datetime, timezone

    from bacteria.app.graph.log import Assertion
    from bacteria.app.graph.repository import SqlGraphRepository
    from bacteria.app.graph.service import owner, refer_to
    from bacteria.app.graph.temporal import OPEN_ENDED, Interval

    now = datetime.now(timezone.utc)
    async with AsyncSession(engine) as db:
        session = await SqlSessionRepository(db).create_session("heard")
        graph = SqlGraphRepository(db)
        me = await owner(graph, "heard", now=now)
        value = await refer_to(graph, "heard", "value", "concise", now=now)
        # Exactly what `_claim` builds for a preference the extractor heard.
        await graph.record(
            [
                Assertion(
                    assertion_id="heard-1",
                    user_id="heard",
                    src=me.node_id,
                    rel="tone",
                    dst=value.node_id,
                    valid=Interval(None, OPEN_ENDED),
                    recorded_at=now,
                    origin="inferred",
                    scope="session",
                    session_id=session.session_id,
                    attrs={"reason": "they asked for short answers"},
                )
            ]
        )
        await db.commit()

        view = await GraphMemoryStore(db).entries(session.session_id, "heard")

    assert view.memory == {}, "the model does not get to write its own memory"
    assert [key for _, key in view.proposals] == ["tone"]
    assert next(iter(view.proposals.values())).reason == "they asked for short answers"


async def test_a_key_the_model_reaches_for_resolves_to_the_catalogues_word(store):
    """Found by the first real turn against this store, as a 500.

    The extractor's relations are canonicalized through aliases and the
    `remember` tool's keys were not, so `user_name` — which the model reaches for
    unprompted — was refused while `name` was accepted. The same word, translated
    on one path and not the other.
    """
    memory, session_id = store

    entry = await memory.remember(
        session_id, USER, "user_name", "Guillermo", "said so", scope=USER_SCOPE
    )

    assert entry.value == "Guillermo"
    view = await memory.entries(session_id, USER)
    assert "name" in view.user_memory, "stored under the catalogue's word"
    assert "user_name" not in view.user_memory


async def test_a_converse_alias_is_not_a_key(store):
    """Swapping is meaningful for a claim and meaningless for a key.

    `mother_of` names the relationship read the other way round, not a spelling
    of it — and a key has one end to hang a value on, so there is nothing for the
    swap to act on.
    """
    memory, session_id = store

    with pytest.raises(UnknownPreferenceError):
        await memory.remember(session_id, USER, "mother_of", "Claudia", "said so")
