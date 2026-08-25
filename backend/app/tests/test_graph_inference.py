"""The succession inference must decline every case it cannot actually deduce.

Each guardrail here protects the same thing: a wrong inference does not fail
loudly, it *explains away a real conflict*. The badge goes quiet, the
contradiction stops being shown, and the system looks more certain than it is —
which is the failure mode the whole undecidable state exists to avoid.

Pure — no database, no fixtures.
"""

from datetime import datetime, timezone

from bacteria.app.graph.catalogue import Relation
from bacteria.app.graph.inference import infer_succession
from bacteria.app.graph.log import Assertion
from bacteria.app.graph.temporal import OPEN_ENDED, Interval

NOW = datetime(2026, 5, 25, tzinfo=timezone.utc)
JAN = datetime(2026, 1, 15, tzinfo=timezone.utc)
FEB = datetime(2026, 2, 15, tzinfo=timezone.utc)

LABELS = {
    "org:acme": "Acme",
    "person:diane": "Diane",
    "person:marta": "Marta",
    "person:bob": "Bob",
}

ONE_CTO = Relation(
    name="cto",
    sentence="<dst> is the CTO of <src>",
    invariant="An organization has one CTO at a time.",
    src_kind="organization",
    dst_kind="person",
    functional=True,
)


def _role(assertion_id: str, holder: str, valid: Interval, *, user: str = "u1") -> Assertion:
    return Assertion(
        assertion_id=assertion_id,
        user_id=user,
        src="org:acme",
        rel="cto",
        dst=holder,
        valid=valid,
        recorded_at=NOW,
    )


ENDED_IN_FEBRUARY = _role("a1", "person:diane", Interval(None, FEB))
OPEN_AND_UNDATED = _role("a2", "person:bob", Interval(None, OPEN_ENDED))


def test_it_infers_when_exactly_one_role_ended_and_one_is_open():
    """The case it is for, so the refusals below mean something."""
    result = infer_succession(
        [ENDED_IN_FEBRUARY, OPEN_AND_UNDATED], ONE_CTO, labels=LABELS, conclusion_id="c", now=NOW
    )

    assert result is not None
    assert result.boundary == FEB


def test_it_declines_when_two_roles_have_ended():
    """Which of the two does the open one follow? Nothing here can say.

    Picking the latest would be plausible and unfounded — the successor may
    follow either, and a vacancy between them is equally consistent.
    """
    also_ended = _role("a3", "person:carol", Interval(None, JAN))

    assert (
        infer_succession(
            [ENDED_IN_FEBRUARY, also_ended, OPEN_AND_UNDATED],
            ONE_CTO,
            labels=LABELS,
            conclusion_id="c",
            now=NOW,
        )
        is None
    )


def test_it_declines_when_two_roles_are_open_and_undated():
    """Two candidate successors is a choice, and there is nothing to choose with.

    This is also the week-3 shape — two current claims, no dates — where the
    right answer is a visible contradiction, not a manufactured handover.
    """
    another_open = _role("a3", "person:carol", Interval(None, OPEN_ENDED))

    assert (
        infer_succession(
            [ENDED_IN_FEBRUARY, OPEN_AND_UNDATED, another_open],
            ONE_CTO,
            labels=LABELS,
            conclusion_id="c",
            now=NOW,
        )
        is None
    )


def test_it_declines_when_a_third_role_spans_the_boundary():
    """A holder covering the moment means the succession was not direct.

    The arithmetic still works — one ended, one is open — and the conclusion
    would be wrong, because someone else held the role across the date being
    inferred.
    """
    interim = _role("a3", "person:carol", Interval(JAN, OPEN_ENDED))

    assert (
        infer_succession(
            [ENDED_IN_FEBRUARY, OPEN_AND_UNDATED, interim],
            ONE_CTO,
            labels=LABELS,
            conclusion_id="c",
            now=NOW,
        )
        is None
    )


def test_it_declines_across_two_peoples_graphs():
    """One person's ended role must never date another person's open one.

    Ownership is checked here as well as in the constraint, because this is a
    second path to the same pair and a guard that exists on only one of them is
    a guard with a way around it.
    """
    someone_elses = _role("a3", "person:bob", Interval(None, OPEN_ENDED), user="u2")

    assert (
        infer_succession(
            [ENDED_IN_FEBRUARY, someone_elses], ONE_CTO, labels=LABELS, conclusion_id="c", now=NOW
        )
        is None
    )


def test_it_ignores_claims_no_longer_believed():
    """A superseded assertion must not license an inference.

    The claim it replaced is still in the log — that is what makes past beliefs
    recoverable — so anything reasoning over the log has to filter by what is
    currently believed rather than by what is present.
    """
    superseded = Assertion(
        assertion_id="a0",
        user_id="u1",
        src="org:acme",
        rel="cto",
        dst="person:diane",
        valid=Interval(None, OPEN_ENDED),
        recorded_at=JAN,
        recorded_until=NOW,
    )

    result = infer_succession(
        [superseded, ENDED_IN_FEBRUARY, OPEN_AND_UNDATED],
        ONE_CTO,
        labels=LABELS,
        conclusion_id="c",
        now=NOW,
    )

    assert result is not None, "the superseded row should not have counted as a third holder"
    assert result.boundary == FEB


def test_the_statement_names_things_a_person_recognizes():
    """A conclusion is read in order to be *disagreed with*, so it must be legible.

    The first real conclusion this system ever drew read "1385501d-... took over
    cto of dcaad500-..." -- correct, and unusable. Node ids are what the engine
    works in; a statement is the one thing here written for a person.
    """
    succession = infer_succession(
        [ENDED_IN_FEBRUARY, OPEN_AND_UNDATED],
        ONE_CTO,
        labels=LABELS,
        conclusion_id="c",
        now=NOW,
    )

    assert succession is not None
    statement = succession.conclusion.statement
    assert "Bob" in statement and "Acme" in statement and "Diane" in statement
    assert "person:" not in statement and "org:" not in statement
    assert "assumed" in statement, "and it must not read as something observed"


def test_an_unknown_label_falls_back_to_the_id_rather_than_failing():
    """A badly named conclusion beats a conclusion that could not be written."""
    succession = infer_succession(
        [ENDED_IN_FEBRUARY, OPEN_AND_UNDATED],
        ONE_CTO,
        labels={},
        conclusion_id="c",
        now=NOW,
    )

    assert succession is not None
    assert "person:bob" in succession.conclusion.statement
