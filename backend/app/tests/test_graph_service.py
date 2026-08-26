"""Observing and revising, with the storage and the rules actually wired together.

The engine's rules are tested without a database in ``test_graph_worked_example.py``
and the mapping is tested in ``test_graph_repository.py``. What is only reachable
here is the *order* the two run in, and the things that go wrong when it is
wrong: a rule evaluated before the write cannot see the claim that just landed,
and a revision that skips the staleness walk leaves beliefs resting on evidence
that moved.

Real Postgres. Start it with `just db-up`.
"""

from dataclasses import replace
from datetime import datetime, timezone

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from bacteria.app.graph.conclusions import Conclusion
from bacteria.app.graph.log import Assertion, supersede
from bacteria.app.graph.repository import SqlGraphRepository
from bacteria.app.graph.service import (
    LabelTakenError,
    MismatchedKindsError,
    claims_for,
    confirm,
    link,
    observe,
    owner,
    preferences_for,
    reject,
    rename,
    retract,
    revise,
)
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
    which is the failure mode of making the guard above too eager. So it is
    *written* — and, since the same triple with a known end is strictly more
    informed than the same triple left open, the open one stops being believed.

    Both halves matter and they pull opposite ways: swallow it and the correction
    is lost, keep both and the log says Diane is currently CTO and also stopped
    being CTO in February.
    """
    await observe(repo, [_cto("a3", "person:diane", Interval(None, OPEN_ENDED), W1)], now=W1)

    outcome = await observe(
        repo, [_cto("a9", "person:diane", Interval(None, FEBRUARY), W3)], now=W3
    )

    assert outcome.recorded == 1, "the correction is written, not swallowed"
    assert [a.assertion_id for a in await repo.current(USER)] == ["a9"]


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


async def test_retracting_one_of_two_claims_ends_the_conflict(repo):
    """The act the console could ask for and had no way to perform.

    A person looking at two mothers for themselves is not correcting a fact --
    they are saying one row should not be believed. That is a statement about
    belief rather than about the world, which is why it closes a row rather than
    asserting a negative.
    """
    claims = [
        _cto("a1", "person:diane", Interval(None, OPEN_ENDED), W1),
        _cto("a2", "person:bob", Interval(None, OPEN_ENDED), W1),
    ]
    first = await observe(repo, claims, now=W1)
    assert [c.state for c in first.conflicts] == ["conflict"]

    outcome = await retract(repo, claims[1], now=W3)

    assert outcome.conflicts == [], "the disagreement is gone, not merely quieter"
    assert outcome.recorded == 0, "nothing was written; a row was closed"
    assert [a.assertion_id for a in await repo.current(USER)] == ["a1"]


async def test_a_retracted_claim_says_which_act_closed_it(repo):
    """`recorded_until` alone cannot tell a correction from a rejection.

    Which matters for the only question anyone will ask of these rows: how often
    was the extractor wrong, as opposed to how often did the world change.
    """
    claim = _cto("a1", "person:diane", Interval(None, OPEN_ENDED), W1)
    await observe(repo, [claim], now=W1)

    await retract(repo, claim, now=W3)

    closed = await repo.assertion(USER, "a1")
    assert closed.closed_by == "retracted"
    assert closed.recorded_until == W3


async def test_retracting_a_premise_stales_what_rested_on_it(repo):
    """A belief whose premise is gone is unexamined, not wrong -- and must say so."""
    ended = _cto("a1", "person:diane", Interval(None, FEBRUARY), W1)
    await observe(repo, [ended], now=W1)
    outcome = await observe(
        repo, [_cto("a2", "person:bob", Interval(None, OPEN_ENDED), W3)], now=W3
    )
    assert len(outcome.inferred) == 1

    retracted = await retract(repo, ended, now=W4)

    assert [c.conclusion_id for c in retracted.stale] == [outcome.inferred[0].conclusion_id]


async def test_a_rejected_conclusion_is_not_proposed_again(repo):
    """The bug this fix exists for, and it was live.

    Rejecting an explanation returns its conflict to `possible`, and `_reconcile`
    infers on `possible` conflicts -- so a fresh active copy of the very
    conclusion the owner had just refused was recorded **inside the rejection
    itself**, before it returned. Not on some later extraction: immediately.

    Asserted on the stored conclusions rather than on the outcome, because the
    outcome looks correct either way once a new explanation exists.
    """
    await observe(repo, [_cto("a1", "person:diane", Interval(None, FEBRUARY), W1)], now=W1)
    first = await observe(repo, [_cto("a2", "person:bob", Interval(None, OPEN_ENDED), W3)], now=W3)
    assert len(first.inferred) == 1

    await reject(repo, USER, first.inferred[0].conclusion_id, now=W4)

    # Anything that re-runs the rules. A re-extraction restating what the log
    # already believes does it: `_unrepeated` drops the claim, `_reconcile` runs.
    again = await observe(repo, [_cto("a2", "person:bob", Interval(None, OPEN_ENDED), W3)], now=W4)
    assert again.recorded == 0, "nothing new was said; only the rules re-ran"

    believed = await repo.current(USER)
    stored = await repo.depending_on(USER, [a.assertion_id for a in believed])
    live = [c for c in stored if c.status == "active"]
    assert live == [], "a rejection has to be remembered, not merely applied"


async def test_rejecting_an_explanation_returns_the_conflict_to_undecided(repo):
    """Honest, rather than resolved: it is the state it was in before anyone assumed."""
    await observe(repo, [_cto("a1", "person:diane", Interval(None, FEBRUARY), W1)], now=W1)
    first = await observe(repo, [_cto("a2", "person:bob", Interval(None, OPEN_ENDED), W3)], now=W3)

    outcome = await reject(repo, USER, first.inferred[0].conclusion_id, now=W4)

    assert [c.state for c in outcome.conflicts] == ["possible"]


async def test_the_owner_can_finally_be_given_their_name(repo):
    """The half of the reserved owner node that was never built.

    Its id is derived from the user id *precisely so* that the label stays
    correctable, and nothing corrected it -- leaving every graph owned by
    somebody called "self".
    """
    me = await owner(repo, USER, now=W1)
    assert me.label == "self"

    renamed = await rename(repo, USER, me.node_id, "Guillermo", now=W3)

    assert renamed.label == "Guillermo"
    assert renamed.node_id == me.node_id, "the id never moves; that is the point"


async def test_a_rename_onto_a_taken_name_is_refused(repo):
    """The hazard that makes rename and link inseparable.

    `node_named` matches on kind and normalized label, so two matching nodes make
    every later mention resolve to whichever the database returns first -- an
    arbitrary answer to "which Diane", drifting toward the one direction ADR 0006
    says cannot be undone.
    """
    me = await owner(repo, USER, now=W1)
    await repo.mint_node(USER, "person", "Guillermo", now=W1)

    with pytest.raises(LabelTakenError):
        await rename(repo, USER, me.node_id, "Guillermo", now=W3)


async def test_a_rename_to_the_name_it_already_has_is_not_a_collision(repo):
    me = await owner(repo, USER, now=W1)
    await rename(repo, USER, me.node_id, "Guillermo", now=W3)

    again = await rename(repo, USER, me.node_id, "Guillermo", now=W4)

    assert again.label == "Guillermo"


async def test_linking_two_nodes_records_a_claim_and_merges_nothing(repo):
    """ADR 0006's identity rule, finally given a writer.

    Both nodes keep their ids and their assertions. What is added is a claim that
    they are one thing -- provenanced, contestable and retractable like any
    other, which is exactly what makes minting a node per distinct name safe.
    """
    me = await owner(repo, USER, now=W1)
    duplicate = await repo.mint_node(USER, "person", "Guillermo", now=W1)

    await link(repo, USER, me.node_id, duplicate.node_id, assertion_id="l1", now=W3)

    assert len(await repo.nodes(USER)) == 2, "linked, never merged"
    claim = await repo.assertion(USER, "l1")
    assert claim.rel == "same_as"
    assert {claim.src, claim.dst} == {me.node_id, duplicate.node_id}


async def test_a_link_across_two_kinds_is_refused(repo):
    """A person is not an organization, and saying so is a slip rather than a merge."""
    person = await repo.mint_node(USER, "person", "Acme", now=W1)
    org = await repo.mint_node(USER, "organization", "Acme", now=W1)

    with pytest.raises(MismatchedKindsError):
        await link(repo, USER, person.node_id, org.node_id, assertion_id="l1", now=W3)


async def test_a_link_can_be_retracted_like_any_other_claim(repo):
    """Which is the whole argument for linking rather than merging."""
    me = await owner(repo, USER, now=W1)
    duplicate = await repo.mint_node(USER, "person", "Guillermo", now=W1)
    await link(repo, USER, me.node_id, duplicate.node_id, assertion_id="l1", now=W3)

    await retract(repo, await repo.assertion(USER, "l1"), now=W4)

    assert [a.assertion_id for a in await repo.current(USER)] == []


def _pref(
    assertion_id: str, rel: str, value: str, *, origin: str, recorded_at, **over
) -> Assertion:
    return Assertion(
        assertion_id=assertion_id,
        user_id=USER,
        src="owner",
        rel=rel,
        dst=value,
        valid=Interval(None, OPEN_ENDED),
        recorded_at=recorded_at,
        origin=origin,
        **over,
    )


async def _seed_prefs(repo, *assertions) -> str:
    """Record preferences against the owner node, whose id is derived."""
    me = await owner(repo, USER, now=W1)
    await repo.record([replace(a, src=me.node_id) for a in assertions])
    return me.node_id


async def test_a_stated_preference_becomes_a_keyed_answer(repo):
    """The relation is the key -- no keying mechanism of its own is needed.

    One slot per key and one dst per (src, rel) at a time are the same statement,
    and the catalogue already made the second.
    """
    value = await repo.mint_node(USER, "value", "concise", now=W1)
    await _seed_prefs(repo, _pref("p1", "tone", value.node_id, origin="stated", recorded_at=W1))

    assert [(p.key, p.value) for p in await preferences_for(repo, USER)] == [("tone", "concise")]


async def test_an_extracted_preference_is_not_spoken(repo):
    """What keeps "memory is written by the owner, not the model" true.

    The model does nearly all of the writing here. It may propose a preference;
    it cannot make its proposal speakable, because everything it writes is
    `inferred` and only an act of the owner's reaches `stated`.
    """
    value = await repo.mint_node(USER, "value", "concise", now=W1)
    await _seed_prefs(repo, _pref("p1", "tone", value.node_id, origin="inferred", recorded_at=W1))

    assert await preferences_for(repo, USER) == []


async def test_a_session_scoped_preference_narrows_rather_than_widens(repo):
    value = await repo.mint_node(USER, "value", "spanish", now=W1)
    await _seed_prefs(
        repo,
        _pref(
            "p1",
            "language",
            value.node_id,
            origin="stated",
            recorded_at=W1,
            scope="session",
            session_id="s1",
        ),
    )

    assert await preferences_for(repo, USER, session_id="s1") != []
    assert await preferences_for(repo, USER, session_id="s2") == []
    assert await preferences_for(repo, USER) == []


async def test_two_answers_for_one_key_resolve_to_the_newer(repo):
    """A caller that asked for the tone needs *an* answer.

    The contradiction is already flagged by the constraint layer, so returning
    nothing here would hide a dispute behind a missing key rather than surface it.
    """
    terse = await repo.mint_node(USER, "value", "concise", now=W1)
    long = await repo.mint_node(USER, "value", "thorough", now=W1)
    await _seed_prefs(
        repo,
        _pref("p1", "tone", terse.node_id, origin="stated", recorded_at=W1),
        _pref("p2", "tone", long.node_id, origin="stated", recorded_at=W3),
    )

    assert [(p.key, p.value) for p in await preferences_for(repo, USER)] == [("tone", "thorough")]


async def test_a_fact_about_a_thing_is_not_a_preference(repo):
    """`mother` is functional and points at a person, so it has no key."""
    await _seed_prefs(repo, _pref("p1", "mother", "person:x", origin="stated", recorded_at=W1))

    assert await preferences_for(repo, USER) == []


async def test_ratifying_what_the_model_guessed_is_not_a_repeat(repo):
    """`origin` is in the repeat key where `trust` deliberately is not.

    A claim arriving through a different channel is news about the channel. The
    owner confirming what the model guessed is news about the world, and
    swallowing it as a restatement would make ratification impossible to record.
    """
    value = await repo.mint_node(USER, "value", "concise", now=W1)
    me = await owner(repo, USER, now=W1)
    guessed = replace(
        _pref("p1", "tone", value.node_id, origin="inferred", recorded_at=W1), src=me.node_id
    )
    await observe(repo, [guessed], now=W1)

    stated = replace(guessed, assertion_id="p2", origin="stated", recorded_at=W3)
    outcome = await observe(repo, [stated], now=W3)

    assert outcome.recorded == 1
    assert [(p.key, p.value) for p in await preferences_for(repo, USER)] == [("tone", "concise")]


async def test_confirming_makes_a_claim_speakable_without_losing_the_proposal(repo):
    """The half of curation nobody had built.

    Every other act on this graph removes. This keeps -- and it is what a
    supplier needs, since a supplier may return only what a person confirmed.
    """
    guessed = _cto("g1", "person:diane", Interval(None, OPEN_ENDED), W1)
    await observe(repo, [guessed], now=W1)
    assert await claims_for(repo, USER) == [], "nothing is speakable yet"

    await confirm(repo, guessed, assertion_id="c1", now=W3)

    spoken = await claims_for(repo, USER)
    assert [c.assertion_id for c in spoken] == ["c1"]
    believed = {a.assertion_id: a.origin for a in await repo.current(USER)}
    assert believed == {"g1": "inferred", "c1": "stated"}, "the proposal survives"


async def test_confirming_twice_writes_nothing_the_second_time(repo):
    """Saying yes twice is one yes, which the repeat rule already knew."""
    guessed = _cto("g1", "person:diane", Interval(None, OPEN_ENDED), W1)
    await observe(repo, [guessed], now=W1)
    await confirm(repo, guessed, assertion_id="c1", now=W3)

    again = await confirm(repo, guessed, assertion_id="c2", now=W4)

    assert again.recorded == 0
    assert len(await claims_for(repo, USER)) == 1


async def test_a_confirmed_claim_reads_as_a_sentence(repo):
    """Node ids are for the engine; this text is for a person or a model.

    Rendered from the catalogue, so a fact reads the way the vocabulary says it
    reads and cannot drift from how a conclusion renders the same relation.
    """
    acme = await repo.mint_node(USER, "organization", "Acme", now=W1)
    diane = await repo.mint_node(USER, "person", "Diane", now=W1)
    claim = Assertion(
        assertion_id="g1",
        user_id=USER,
        src=acme.node_id,
        rel="cto",
        dst=diane.node_id,
        valid=Interval(None, OPEN_ENDED),
        recorded_at=W1,
        attrs={"reason": "they said Diane runs engineering"},
    )
    await observe(repo, [claim], now=W1)

    await confirm(repo, claim, assertion_id="c1", now=W3)

    spoken = await claims_for(repo, USER)
    assert spoken[0].statement == "Diane is the CTO of Acme"
    assert spoken[0].reason == "they said Diane runs engineering"


async def test_an_unconfirmed_claim_never_becomes_a_candidate(repo):
    """The rule the whole record rests on: an index ranks, it does not speak."""
    await observe(repo, [_cto("g1", "person:diane", Interval(None, OPEN_ENDED), W1)], now=W1)

    assert await claims_for(repo, USER) == []


async def test_anchors_narrow_to_claims_touching_those_nodes(repo):
    """What a supplier will use once it has resolved a message to some nodes."""
    other = _cto("g2", "person:bob", Interval(None, OPEN_ENDED), W1)
    first = _cto("g1", "person:diane", Interval(None, OPEN_ENDED), W1)
    await observe(repo, [first], now=W1)
    await confirm(repo, first, assertion_id="c1", now=W3)
    await observe(repo, [other], now=W3)
    await confirm(repo, other, assertion_id="c2", now=W4)

    narrowed = await claims_for(repo, USER, anchors=["person:diane"])

    assert [c.assertion_id for c in narrowed] == ["c1"]


async def test_a_dated_claim_closes_the_open_one_it_corrects(repo):
    """The case a real conversation produced, in one sentence.

    "Diane is Acme's CTO", then "Diane left in February". Same triple, one open
    and one ended -- not two beliefs about the world, but the second being the
    first plus when it stopped.
    """
    open_claim = _cto("a1", "person:diane", Interval(None, OPEN_ENDED), W1)
    await observe(repo, [open_claim], now=W1)

    await observe(repo, [_cto("a2", "person:diane", Interval(None, FEBRUARY), W3)], now=W3)

    believed = {a.assertion_id for a in await repo.current(USER)}
    assert believed == {"a2"}, "the open claim is no longer believed"
    closed = await repo.assertion(USER, "a1")
    assert closed.closed_by == "superseded", "and the log says which act closed it"


async def test_it_unblocks_the_succession_the_stale_claim_was_hiding(repo):
    """The second harm, which is quieter than the contradiction.

    Two open undated claims make `infer_succession` decline, so the stale row
    suppressed the very inference the correction should have enabled.
    """
    await observe(repo, [_cto("a1", "person:diane", Interval(None, OPEN_ENDED), W1)], now=W1)

    outcome = await observe(
        repo,
        [
            _cto("a2", "person:diane", Interval(None, FEBRUARY), W3),
            _cto("a3", "person:marta", Interval(None, OPEN_ENDED), W3),
        ],
        now=W3,
    )

    assert len(outcome.inferred) == 1
    assert [c.state for c in outcome.conflicts] == ["explained"]


async def test_a_different_object_is_a_disagreement_and_stays_one(repo):
    """ "Actually it was Bob" is not a correction this may make silently.

    Different `dst`, so there is nothing arithmetic about it -- it needs a person,
    and closing it here would be the model unbelieving something nobody retracted.
    """
    await observe(repo, [_cto("a1", "person:diane", Interval(None, OPEN_ENDED), W1)], now=W1)

    outcome = await observe(repo, [_cto("a2", "person:bob", Interval(None, FEBRUARY), W3)], now=W3)

    believed = {a.assertion_id for a in await repo.current(USER)}
    assert believed == {"a1", "a2"}, "both stand"
    assert outcome.conflicts != [], "and the disagreement is reported"


async def test_an_open_claim_does_not_close_another_open_one(repo):
    """Two current claims are a contradiction, which is not this rule's business."""
    await observe(repo, [_cto("a1", "person:diane", Interval(None, OPEN_ENDED), W1)], now=W1)

    await observe(repo, [_cto("a2", "person:diane", Interval(W3, OPEN_ENDED), W3)], now=W3)

    assert len(await repo.current(USER)) == 2


async def test_a_withdrawn_start_is_not_recorded_as_one_that_was_said(repo):
    """A row whose valid_from is null while attrs say the date was said misreports.

    Extraction writes `since_said` meaning *the transcript supported this*, and
    stripping the start here makes that untrue. A log that misreports its own
    decision is worse than one that says nothing, because it would be believed.
    """
    ended = _cto("a1", "person:diane", Interval(None, FEBRUARY), W1)
    successor = replace(
        _cto("a2", "person:marta", Interval(FEBRUARY, OPEN_ENDED), W1),
        attrs={"reason": "Marta took over [in February]", "since_said": "2026-02"},
    )

    await observe(repo, [ended, successor], now=W1)

    stored = await repo.assertion(USER, "a2")
    assert stored.valid.start is None
    assert stored.attrs == {
        "reason": "Marta took over [in February]",
        "since_withdrawn": "2026-02",
    }
