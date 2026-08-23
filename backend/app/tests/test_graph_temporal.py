"""Overlap has three answers, and every caller has to face all three.

The whole temporal layer rests on this one function. If it ever collapses
"cannot be determined" into either neighbour, the damage is silent: rounding to
``False`` hides real contradictions, and rounding to ``True`` invents ones that
send a person to review something the system was never unsure about.

Pure — no database, no fixtures.
"""

from datetime import datetime, timezone

from bacteria.app.graph.temporal import ALWAYS, OPEN_ENDED, Interval, overlaps

JAN = datetime(2026, 1, 1, tzinfo=timezone.utc)
FEB = datetime(2026, 2, 1, tzinfo=timezone.utc)
MAR = datetime(2026, 3, 1, tzinfo=timezone.utc)
APR = datetime(2026, 4, 1, tzinfo=timezone.utc)


def test_two_open_intervals_overlap_however_unknown_their_starts():
    """Both are true *now*, so they share the present whatever came before.

    This is the case that makes a contradiction between two current claims
    detectable at all. Without it, "she is their CTO" and "he is their CTO" —
    neither carrying a start date, which is how people speak — would be
    undecidable rather than a conflict, and the one contradiction a user would
    certainly want to see would be the one never shown.
    """
    diane = Interval(None, OPEN_ENDED)
    bob = Interval(None, OPEN_ENDED)

    assert overlaps(diane, bob) is True


def test_a_closed_interval_before_another_does_not_overlap_it():
    """Provably apart, so a succession is not reported as a contradiction."""
    assert overlaps(Interval(JAN, FEB), Interval(MAR, APR)) is False
    assert overlaps(Interval(MAR, APR), Interval(JAN, FEB)) is False


def test_touching_intervals_do_not_overlap():
    """One ending exactly where the next begins is a handover, not a clash.

    Half-open on the closing side. Treating it as an overlap would make every
    correctly recorded succession produce a conflict at the instant of handover,
    which is the case the succession inference exists to *resolve*.
    """
    assert overlaps(Interval(JAN, MAR), Interval(MAR, APR)) is False


def test_an_unknown_bound_makes_the_answer_undecidable():
    """Neither claim can be proven to sit outside the other, so neither answer is honest.

    The successor's start is unknown, so it may or may not predate the
    predecessor's end. Returning ``False`` here would be the dangerous rounding:
    it would state there is no contradiction when nobody knows.
    """
    ended_in_february = Interval(None, FEB)
    still_running = Interval(None, OPEN_ENDED)

    assert overlaps(ended_in_february, still_running) is None


def test_a_known_start_after_a_known_end_resolves_the_undecidable_case():
    """Learning one date is all it takes, which is why the state is worth keeping.

    Same pair as above with the successor's start supplied. A ``possible``
    conflict becomes settled by one fact arriving — the reason undecidable is a
    state to render rather than an error to raise.
    """
    assert overlaps(Interval(None, FEB), Interval(FEB, OPEN_ENDED)) is False


def test_the_sentinels_bound_everything_without_special_cases():
    """``ALWAYS`` precedes and ``OPEN_ENDED`` follows every real timestamp.

    They are ordinary comparisons, which is why the overlap rule needs no branch
    for them. If either stopped being extreme, an always-true fact would sort
    into the middle of history and stop overlapping things it contains.
    """
    forever = Interval(ALWAYS, OPEN_ENDED)

    assert overlaps(forever, Interval(JAN, FEB)) is True
    assert overlaps(Interval(JAN, FEB), forever) is True


def test_an_interval_is_open_only_when_asserted_to_be():
    """An undated end is unknown, not open — the distinction the layer exists for."""
    assert Interval(JAN, OPEN_ENDED).is_open
    assert not Interval(JAN, None).is_open
    assert not Interval(JAN, FEB).is_open
