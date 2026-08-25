"""Four weeks of ordinary input, driven through the whole engine.

The acceptance test for the memory graph, and the reason it is worth having as
one case rather than as six unit tests: every mechanism ADR 0006 describes is
exercised *in the order a real conversation would exercise them*, and the parts
that only misbehave in combination are the parts that hurt. Two of the four
claims here were false in the design's prose and were only found by running it.

| Week | Input                                                          |
|------|----------------------------------------------------------------|
| 1    | "Had coffee with Diane from Acme — she's their CTO."            |
| 2    | An email from Diana Mercer; a conclusion is drawn about Diane.  |
| 3    | A newsletter says Acme's CTO is Bob Restrepo.                   |
| 4    | "Actually Diane left Acme back in February."                    |

What each week is *for*: week 1 records a claim with no start date, which is how
people speak and what everything downstream has to survive. Week 2 draws a
conclusion so there is something for week 4 to invalidate. Week 3 introduces a
contradiction the system must hold rather than resolve. Week 4 arrives
bi-temporally — recorded in week 4, valid from February, before everything above.

Pure: no database, no fixtures, no model.
"""

from datetime import datetime, timezone

from bacteria.app.graph.catalogue import Relation
from bacteria.app.graph.conclusions import Conclusion, stale_after
from bacteria.app.graph.constraints import conflicts_for
from bacteria.app.graph.inference import infer_succession
from bacteria.app.graph.log import Assertion, state_at, supersede
from bacteria.app.graph.temporal import OPEN_ENDED, Interval

W1 = datetime(2026, 5, 4, tzinfo=timezone.utc)
W2 = datetime(2026, 5, 11, tzinfo=timezone.utc)
W3 = datetime(2026, 5, 18, tzinfo=timezone.utc)
W4 = datetime(2026, 5, 25, tzinfo=timezone.utc)
FEBRUARY = datetime(2026, 2, 15, tzinfo=timezone.utc)

ONE_CTO = Relation(
    name="cto",
    sentence="<dst> is the CTO of <src>",
    invariant="An organization has one CTO at a time.",
    src_kind="organization",
    dst_kind="person",
    functional=True,
)
USER = "user-1"


def _role(assertion_id: str, holder: str, valid: Interval, recorded_at: datetime) -> Assertion:
    return Assertion(
        assertion_id=assertion_id,
        user_id=USER,
        src="org:acme",
        rel="cto",
        dst=holder,
        valid=valid,
        recorded_at=recorded_at,
    )


def _four_weeks() -> tuple[list[Assertion], list[Conclusion]]:
    """The log as it stands at the end of week 4, and the beliefs drawn from it."""
    # Week 1. Present tense, so the end is open — not merely undated.
    diane = _role("a3", "person:diane", Interval(None, OPEN_ENDED), W1)

    # Week 2. A belief resting on the week-1 claim.
    c1 = Conclusion(
        conclusion_id="c1",
        user_id=USER,
        statement="Diane is the decision-maker for the Acme integration",
        evidence=("a3",),
        confidence=0.72,
        derived_by="llm-judgment",
        recorded_at=W2,
    )

    # Week 3. The newsletter lands; nothing is rejected or overwritten.
    bob = _role("a7", "person:bob", Interval(None, OPEN_ENDED), W3)

    # Week 4. Append-only: belief in `a3` closes and `a8` states the same claim
    # with the end we now know. `a3` is kept, which is what makes week 2's
    # conclusion still explicable.
    closed_diane, corrected = supersede(
        diane, assertion_id="a8", valid=Interval(None, FEBRUARY), at=W4
    )
    return [closed_diane, bob, corrected], [c1]


def test_week_three_is_a_contradiction_rather_than_a_correction():
    """Both claims are believed, and the conflict is reported as certain.

    Neither has a start date, and both are asserted to hold now, so they
    provably collide in the present. A system that resolved this automatically
    would pick one and be wrong about half the time; a system that could not see
    it would be worse.
    """
    assertions, _ = _four_weeks()
    at_week_three = state_at(assertions, W3)

    conflicts = conflicts_for(ONE_CTO, at_week_three)

    assert [c.state for c in conflicts] == ["conflict"]
    assert {conflicts[0].left, conflicts[0].right} == {"a3", "a7"}


def test_week_four_leaves_the_conflict_undecided_rather_than_resolving_it():
    """Closing Diane's role does *not* clear the badge, and the prose said it did.

    Bob's start is unknown too — the newsletter never gave one — so nothing
    proves the two roles apart, and the honest state is ``possible``. This was
    asserted as a clean self-resolution in the design and was false; running it
    is what found that.
    """
    assertions, _ = _four_weeks()
    at_week_four = state_at(assertions, W4)

    conflicts = conflicts_for(ONE_CTO, at_week_four)

    assert [c.state for c in conflicts] == ["possible"]


def test_an_inference_explains_the_conflict_without_writing_a_date_anywhere():
    """The badge becomes ``explained``: a citation and a confidence, not a silence.

    The assumed boundary lives in the conclusion. If it were written onto the
    successor's assertion the two intervals would be provably apart and the
    conflict would vanish outright — taking the assumption out of sight at the
    moment it started carrying weight, and letting the next inference read a
    guess as an observation.
    """
    assertions, _ = _four_weeks()
    at_week_four = state_at(assertions, W4)

    succession = infer_succession(at_week_four, ONE_CTO, conclusion_id="c2", now=W4)

    assert succession is not None
    assert succession.boundary == FEBRUARY
    assert set(succession.conclusion.evidence) == {"a8", "a7"}
    assert succession.conclusion.derived_by == "constraint-inference"

    explained = conflicts_for(ONE_CTO, at_week_four, conclusions=[succession.conclusion])
    assert [c.state for c in explained] == ["explained"]

    # The claim itself is untouched: no assumed start reached the log.
    successor = next(a for a in at_week_four if a.assertion_id == "a7")
    assert successor.valid.start is None


def test_retracting_the_assumption_returns_the_conflict_to_undecided():
    """Defeasible in practice, not only in principle.

    Nothing has to be un-written, because nothing was written — the conflict goes
    back to the state it was in before anyone assumed anything, which is the
    property that makes the assumption safe to make automatically.
    """
    assertions, _ = _four_weeks()
    at_week_four = state_at(assertions, W4)
    succession = infer_succession(at_week_four, ONE_CTO, conclusion_id="c2", now=W4)
    assert succession is not None

    withdrawn = [Conclusion(**{**succession.conclusion.__dict__, "status": "retracted"})]

    assert [c.state for c in conflicts_for(ONE_CTO, at_week_four, conclusions=withdrawn)] == [
        "possible"
    ]


def test_the_week_two_conclusion_goes_stale_when_its_evidence_is_revised():
    """Stale, not wrong: a sound inference whose premise moved.

    ``c1`` cited ``a3``, and week 4 superseded it. Without this walk the system
    keeps asserting a belief it has the evidence to doubt, and nothing anywhere
    records that it should be looked at again.
    """
    _, conclusions = _four_weeks()

    changed = stale_after(conclusions, ["a3"])

    assert [c.conclusion_id for c in changed] == ["c1"]
    assert changed[0].status == "stale"


def test_what_was_believed_in_week_two_is_still_recoverable_in_week_four():
    """The correction does not rewrite the past, which is what recorded time buys.

    Replaying a past run means reconstructing the memory that run saw. In week 2
    this system believed Diane's role was open-ended; that belief is wrong now
    and was held then, and both have to remain true statements.
    """
    assertions, _ = _four_weeks()

    believed_then = {a.assertion_id for a in state_at(assertions, W2)}

    assert "a3" in believed_then
    assert "a8" not in believed_then, "week 4's correction must not appear in week 2"
    assert next(a for a in assertions if a.assertion_id == "a3").valid.is_open
