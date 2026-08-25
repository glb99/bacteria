"""The boundary where rows become values, and what it must not lose.

Two things are tested here and nothing else is worth a database. First, that the
three bound states survive the round trip: a known date, the open sentinel, and
``NULL`` for unknown are three different meanings sharing one column, and if the
mapping flattens any pair of them the temporal layer above starts answering
confidently and wrongly. Second, that ownership is in the query — a graph
belonging to someone else must be unreachable, not merely unreturned.

The engine's own behaviour is covered without a database in
``test_graph_worked_example.py``; repeating it here would cost every run the
same seconds to assert the same thing.

Real Postgres, like everything else in this suite. Start it with `just db-up`.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from bacteria.app.graph.conclusions import Conclusion
from bacteria.app.graph.log import Assertion, supersede
from bacteria.app.graph.repository import (
    SqlGraphRepository,
    UnknownAssertionError,
    UnknownConclusionError,
    tally_relations,
)
from bacteria.app.graph.temporal import OPEN_ENDED, Interval

JAN = datetime(2026, 1, 15, tzinfo=timezone.utc)
FEB = datetime(2026, 2, 15, tzinfo=timezone.utc)
NOW = datetime(2026, 5, 25, tzinfo=timezone.utc)


def _assertion(
    assertion_id: str, valid: Interval, *, user: str = "u1", dst: str = "person:diane"
) -> Assertion:
    return Assertion(
        assertion_id=assertion_id,
        user_id=user,
        src="org:acme",
        rel="cto",
        dst=dst,
        valid=valid,
        recorded_at=JAN,
    )


@pytest.fixture(name="repo")
async def _repo(engine):
    async with AsyncSession(engine) as session:
        yield SqlGraphRepository(session)
        await session.commit()


async def test_all_three_bound_states_survive_the_round_trip(repo):
    """Known, open and unknown must come back as three distinct things.

    They share one nullable column, so the mapping is the only thing keeping
    them apart. Flatten open into unknown and every current fact becomes merely
    undated — which makes two current claims undecidable instead of conflicting,
    and quietly removes the one contradiction a person would certainly want.
    """
    await repo.record(
        [
            # Three different holders, because the unique constraint on
            # (user_id, src, rel, dst, recorded_at) forbids one person
            # claiming the same role three ways at the same instant -- which
            # is the constraint doing its job, and was found by writing this
            # test with one holder.
            _assertion("known", Interval(JAN, FEB), dst="person:diane"),
            _assertion("open", Interval(JAN, OPEN_ENDED), dst="person:bob"),
            _assertion("unknown", Interval(None, None), dst="person:carol"),
        ]
    )

    stored = {a.assertion_id: a for a in await repo.current("u1")}

    assert stored["known"].valid == Interval(JAN, FEB)
    assert stored["open"].valid.end == OPEN_ENDED
    assert stored["open"].valid.is_open
    assert stored["unknown"].valid == Interval(None, None)
    assert not stored["unknown"].valid.is_open, "unknown must not read as open"


async def test_timestamps_come_back_timezone_aware(repo):
    """A naive datetime compares as local time, and every rule here compares.

    Postgres honours `DateTime(timezone=True)`, so this passes today. It is here
    because the boundary is where that promise is either kept or quietly dropped,
    and the failure is invisible: comparisons still work, against the wrong
    instant.
    """
    await repo.record([_assertion("a1", Interval(JAN, OPEN_ENDED))])

    stored = (await repo.current("u1"))[0]

    assert stored.recorded_at.tzinfo is not None
    assert stored.valid.start is not None and stored.valid.start.tzinfo is not None


async def test_a_superseded_claim_leaves_the_log_and_stays_in_history(repo):
    """The correction changes what is believed without erasing what was.

    This is the property recorded time exists for: replaying a past run means
    reconstructing the memory that run saw. If supersession deleted the old row,
    every past belief would silently become the current one.
    """
    original = _assertion("a3", Interval(None, OPEN_ENDED))
    await repo.record([original])

    closed, replacement = supersede(original, assertion_id="a8", valid=Interval(None, FEB), at=NOW)
    await repo.supersede(closed, replacement)

    now_believed = {a.assertion_id for a in await repo.current("u1")}
    assert now_believed == {"a8"}

    before_the_correction = {
        a.assertion_id for a in await repo.believed_at("u1", NOW - timedelta(days=1))
    }
    assert before_the_correction == {"a3"}


async def test_a_revision_and_its_replacement_never_overlap(repo):
    """At the instant of supersession exactly one of the two is believed.

    Both counting would give every correction a zero-width contradiction, and
    the functional constraint would report a conflict for a fact that was only
    ever held by one person.
    """
    original = _assertion("a3", Interval(None, OPEN_ENDED))
    await repo.record([original])
    closed, replacement = supersede(original, assertion_id="a8", valid=Interval(None, FEB), at=NOW)
    await repo.supersede(closed, replacement)

    at_the_instant = {a.assertion_id for a in await repo.believed_at("u1", NOW)}

    assert at_the_instant == {"a8"}


async def test_conclusions_are_reachable_backwards_from_their_evidence(repo):
    """The walk that justifies the layer: revised assertion to dependent belief.

    Without it a revision leaves conclusions standing on evidence that moved,
    with nothing anywhere recording that they should be looked at again — which
    makes this an audit log rather than a memory that self-corrects.
    """
    await repo.record([_assertion("a3", Interval(None, OPEN_ENDED))])
    await repo.record_conclusion(
        Conclusion(
            conclusion_id="c1",
            user_id="u1",
            statement="Diane is the decision-maker",
            evidence=("a3",),
            confidence=0.72,
            derived_by="llm-judgment",
            recorded_at=JAN,
        )
    )

    dependents = await repo.depending_on("u1", ["a3"])

    assert [c.conclusion_id for c in dependents] == ["c1"]
    assert dependents[0].evidence == ("a3",)
    assert await repo.depending_on("u1", ["a-nobody-cited"]) == []


async def test_one_persons_graph_is_unreachable_from_another(repo):
    """Ownership is in the query, not a filter someone remembers to apply.

    `chat/access.py` records what forgetting looks like here — an ownership rule
    per feature, forgotten silently, with nothing in the build to notice. This is
    that notice for the graph.
    """
    await repo.record(
        [
            _assertion("mine", Interval(JAN, FEB), user="u1"),
            _assertion("theirs", Interval(JAN, FEB), user="u2"),
        ]
    )

    assert {a.assertion_id for a in await repo.current("u1")} == {"mine"}
    assert {a.assertion_id for a in await repo.believed_at("u1", NOW)} == {"mine"}


async def test_writing_across_owners_is_refused_rather_than_silently_scoped(repo):
    """A guessed id belonging to someone else must fail, and fail indistinguishably.

    Same error for "no such assertion" and "not yours", because a caller that can
    tell them apart can enumerate the second by guessing.
    """
    await repo.record([_assertion("theirs", Interval(JAN, OPEN_ENDED), user="u2")])
    theirs = _assertion("theirs", Interval(JAN, OPEN_ENDED), user="u1")
    closed, replacement = supersede(theirs, assertion_id="new", valid=Interval(JAN, FEB), at=NOW)

    with pytest.raises(UnknownAssertionError):
        await repo.supersede(closed, replacement)

    with pytest.raises(UnknownAssertionError):
        await repo.supersede(
            *supersede(
                _assertion("absent", Interval(JAN, FEB)),
                assertion_id="n",
                valid=Interval(JAN, FEB),
                at=NOW,
            )
        )


async def test_a_conclusion_status_cannot_be_changed_across_owners(repo):
    """The same scoping on the write path that reads already have."""
    await repo.record([_assertion("a3", Interval(None, OPEN_ENDED), user="u2")])
    await repo.record_conclusion(
        Conclusion(
            conclusion_id="c1",
            user_id="u2",
            statement="theirs",
            evidence=("a3",),
            confidence=0.5,
            derived_by="llm-judgment",
            recorded_at=JAN,
        )
    )

    with pytest.raises(UnknownConclusionError):
        await repo.set_status("u1", "c1", "stale")

    await repo.set_status("u2", "c1", "stale")
    assert (await repo.depending_on("u2", ["a3"]))[0].status == "stale"


async def test_the_relation_tally_counts_across_every_owner(engine):
    """The one unscoped read here, and the scope is the point.

    The catalogue is a single literal shared by everybody, so whether a relation
    is worth promoting is a question about the extractor's output rather than
    about anyone's graph. Tallied per user, a name that nine people each used
    twice would never reach the rule of three.
    """
    async with AsyncSession(engine) as session:
        repo = SqlGraphRepository(session)
        await repo.record(
            [
                _assertion("t1", Interval(None, OPEN_ENDED), user="tally-a", dst="person:one"),
                _assertion("t2", Interval(None, OPEN_ENDED), user="tally-b", dst="person:two"),
            ]
        )
        await session.commit()

        tally = await tally_relations(session)

    assert tally["cto"] >= 2, "both owners' rows are counted, not one owner's"
