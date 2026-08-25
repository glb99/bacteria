"""Observing and revising, with the storage and the rules actually wired together.

The engine's rules are tested without a database in ``test_graph_worked_example.py``
and the mapping is tested in ``test_graph_repository.py``. What is only reachable
here is the *order* the two run in, and the things that go wrong when it is
wrong: a rule evaluated before the write cannot see the claim that just landed,
and a revision that skips the staleness walk leaves beliefs resting on evidence
that moved.

Real Postgres. Start it with `just db-up`.
"""

from datetime import datetime, timezone

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from bacteria.app.graph.conclusions import Conclusion
from bacteria.app.graph.log import Assertion, supersede
from bacteria.app.graph.repository import SqlGraphRepository
from bacteria.app.graph.service import observe, revise
from bacteria.app.graph.temporal import OPEN_ENDED, Interval

W1 = datetime(2026, 5, 4, tzinfo=timezone.utc)
W3 = datetime(2026, 5, 18, tzinfo=timezone.utc)
W4 = datetime(2026, 5, 25, tzinfo=timezone.utc)
FEBRUARY = datetime(2026, 2, 15, tzinfo=timezone.utc)
USER = "u1"


def _cto(assertion_id: str, holder: str, valid: Interval, recorded_at: datetime) -> Assertion:
    return Assertion(
        assertion_id=assertion_id,
        user_id=USER,
        src="org:acme",
        rel="cto",
        dst=holder,
        valid=valid,
        recorded_at=recorded_at,
    )


@pytest.fixture(name="repo")
async def _repo(engine):
    async with AsyncSession(engine) as session:
        yield SqlGraphRepository(session)
        await session.commit()


async def test_a_second_current_claim_is_reported_as_a_conflict(repo):
    """Both are believed and both are open, so they collide in the present.

    The rules run after the write, which is the whole reason this module exists.
    Evaluated before it, the newsletter's claim would be compared against a graph
    that did not contain it and nothing would be found.
    """
    await observe(repo, [_cto("a3", "person:diane", Interval(None, OPEN_ENDED), W1)], now=W1)

    outcome = await observe(
        repo, [_cto("a7", "person:bob", Interval(None, OPEN_ENDED), W3)], now=W3
    )

    assert [c.state for c in outcome.conflicts] == ["conflict"]
    assert outcome.needs_attention


async def test_two_colliding_claims_in_one_batch_are_still_seen(repo):
    """A conflict inside a single write must not be invisible.

    This is the case that fails if the rules are evaluated against the graph as
    it was and the batch is applied afterwards — each claim would be checked
    against a world that did not yet contain the other.
    """
    outcome = await observe(
        repo,
        [
            _cto("a3", "person:diane", Interval(None, OPEN_ENDED), W1),
            _cto("a7", "person:bob", Interval(None, OPEN_ENDED), W1),
        ],
        now=W1,
    )

    assert [c.state for c in outcome.conflicts] == ["conflict"]


async def test_an_undated_pair_is_possible_rather_than_a_conflict(repo):
    """Undated claims are the normal case and must not fill a review queue.

    ``needs_attention`` is false here on purpose: a person cannot act on "these
    two might overlap, nobody knows when either started", and a badge raised for
    every such pair is a badge that stops being read.
    """
    await observe(repo, [_cto("a1", "person:diane", Interval(None, None), W1)], now=W1)

    outcome = await observe(repo, [_cto("a2", "person:bob", Interval(None, None), W3)], now=W3)

    assert [c.state for c in outcome.conflicts] == ["possible"]
    assert not outcome.needs_attention


async def test_a_revision_explains_the_conflict_and_stales_what_rested_on_it(repo):
    """Week 4, end to end: correct a claim and watch both consequences fire.

    The conflict becomes ``explained`` — not cleared, because the successor's
    start is still unknown — and the belief that cited the corrected assertion is
    marked stale. Neither happens without this module putting the repository and
    the engine in the right order.
    """
    diane = _cto("a3", "person:diane", Interval(None, OPEN_ENDED), W1)
    await observe(repo, [diane], now=W1)
    await repo.record_conclusion(
        Conclusion(
            conclusion_id="c1",
            user_id=USER,
            statement="Diane is the decision-maker for the Acme integration",
            evidence=("a3",),
            confidence=0.72,
            derived_by="llm-judgment",
            recorded_at=W1,
        )
    )
    await observe(repo, [_cto("a7", "person:bob", Interval(None, OPEN_ENDED), W3)], now=W3)

    closed, corrected = supersede(diane, assertion_id="a8", valid=Interval(None, FEBRUARY), at=W4)
    outcome = await revise(repo, closed, corrected, now=W4)

    assert [c.conclusion_id for c in outcome.stale] == ["c1"]
    assert [c.state for c in outcome.conflicts] == ["explained"]


async def test_observing_twice_does_not_accumulate_explanations(repo):
    """Idempotence, and it falls out of only inferring on ``possible``.

    A conflict already carrying an active explanation reads as ``explained`` and
    is skipped. Without that, a re-run — a retried job, a replayed batch — would
    record a second identical conclusion every time, and the review surface would
    show one contradiction explained five ways.
    """
    diane = _cto("a3", "person:diane", Interval(None, FEBRUARY), W1)
    bob = _cto("a7", "person:bob", Interval(None, OPEN_ENDED), W3)
    await observe(repo, [diane], now=W1)

    first = await observe(repo, [bob], now=W3)
    second = await observe(repo, [], now=W4)
    third = await observe(repo, [_cto("a9", "person:diane", Interval(None, FEBRUARY), W4)], now=W4)

    assert len(first.inferred) == 1
    assert second.inferred == []
    assert third.inferred == [], "an existing explanation must suppress a second one"

    explanations = await repo.depending_on(USER, ["a7"])
    assert len([c for c in explanations if c.derived_by == "constraint-inference"]) == 1


async def test_an_empty_observation_changes_nothing(repo):
    """Nothing to write, so nothing to evaluate and no queries to pay for."""
    outcome = await observe(repo, [], now=W1)

    assert outcome.conflicts == []
    assert outcome.inferred == []
    assert not outcome.needs_attention


async def test_a_claim_the_log_already_believes_is_not_written_again(repo):
    """A fact restated next week is not a second fact.

    The deterministic assertion id does not cover this and looked like it did.
    It hashes the run's timestamp, deliberately, so that a genuine later
    observation does not collide with the first — which means it collapses a
    retried job and nothing else. Without this guard every re-mention appends a
    believed copy and the projection returns N identical edges for one
    relationship, which is what three mentions of the same parent in one
    afternoon produced in real use.
    """
    await observe(repo, [_cto("a3", "person:diane", Interval(None, OPEN_ENDED), W1)], now=W1)

    outcome = await observe(
        repo, [_cto("a9", "person:diane", Interval(None, OPEN_ENDED), W3)], now=W3
    )

    assert outcome.recorded == 0
    assert len(await repo.current(USER)) == 1


async def test_the_same_pair_over_a_different_span_is_not_a_repeat(repo):
    """ "She was their CTO until February" is not a restatement of "she is".

    Keyed on the triple alone this would be swallowed and the correction lost,
    which is the failure mode of making the guard above too eager. It is not a
    revision either — nothing produces one from an extraction — so it lands
    beside the first and the constraint layer is left to report the pair.
    """
    await observe(repo, [_cto("a3", "person:diane", Interval(None, OPEN_ENDED), W1)], now=W1)

    outcome = await observe(
        repo, [_cto("a9", "person:diane", Interval(None, FEBRUARY), W3)], now=W3
    )

    assert outcome.recorded == 1
    assert len(await repo.current(USER)) == 2


async def test_a_claim_repeated_inside_one_batch_is_written_once(repo):
    """A model returning the same claim twice must not produce two rows.

    Given ids minted the way extraction mints them the database would collapse
    these anyway — same instant, same claim, same id, and ``record`` ignores
    primary-key conflicts. Distinct ids here on purpose: the guarantee belongs to
    the service, so a writer that mints ids some other way still gets it, and the
    count reported back does not claim writes that never happened.
    """
    outcome = await observe(
        repo,
        [
            _cto("a3", "person:diane", Interval(None, OPEN_ENDED), W1),
            _cto("a4", "person:diane", Interval(None, OPEN_ENDED), W1),
        ],
        now=W1,
    )

    assert outcome.recorded == 1
    assert len(await repo.current(USER)) == 1


async def test_a_succession_the_model_performed_is_taken_back_and_re_derived(repo):
    """The live failure, verbatim: "Diane left in February 2026, Marta took over".

    The extractor gave Marta a start equal to Diane's end. Nobody stated it -- the
    model performed the succession itself, which the prompt forbids and which two
    prose-reading guards failed to catch, the second because the model wrote the
    date into its own justification.

    It matters which side does it. An extractor writing that boundary produces an
    assertion, indistinguishable from an observation. The engine writing it
    produces a conclusion carrying confidence and evidence -- and supplying the
    start is what removed the engine's precondition, so the guess also silenced
    the machinery that would have marked it as one.
    """
    outcome = await observe(
        repo,
        [
            _cto("d1", "person:diane", Interval(None, FEBRUARY), W1),
            _cto("m1", "person:marta", Interval(FEBRUARY, OPEN_ENDED), W1),
        ],
        now=W1,
    )

    believed = {a.assertion_id: a for a in await repo.current(USER)}
    assert believed["m1"].valid.start is None, "the assumed start must not be a fact"
    assert believed["d1"].valid.end == FEBRUARY, "the stated end is untouched"

    assert len(outcome.inferred) == 1, "and the same boundary arrives as an assumption"
    conclusion = outcome.inferred[0]
    assert conclusion.confidence < 1.0
    assert set(conclusion.evidence) == {"d1", "m1"}


async def test_a_start_matching_nothing_survives(repo):
    """Only the succession signature is stripped, not every stated start."""
    await observe(repo, [_cto("d1", "person:diane", Interval(None, FEBRUARY), W1)], now=W1)

    await observe(repo, [_cto("m1", "person:marta", Interval(W3, OPEN_ENDED), W4)], now=W4)

    believed = {a.assertion_id: a for a in await repo.current(USER)}
    assert believed["m1"].valid.start == W3
