"""A stated date becomes a bound; everything else stays unknown.

The field exists because `valid_from` was null on every row ever written, which
left succession inference with no boundary it could fire on. The risk it
introduces is the opposite one: a model asked for a date will supply one, and an
invented start is worse than no start because it is checkable-looking and wrong.

So most of these assert a refusal.

Pure — no database, no model, no fixtures.
"""

from datetime import datetime, timezone

from bacteria.app.graph.dates import parse_bound
from bacteria.app.graph.extraction import _interval
from bacteria.app.graph.temporal import OPEN_ENDED


def test_a_full_date_is_taken_as_written():
    assert parse_bound("2019-03-04") == datetime(2019, 3, 4, tzinfo=timezone.utc)


def test_a_month_resolves_to_its_first_instant():
    """ADR 0006's worked example is "she left in February", so this must work.

    Requiring a full date would have made the design's own canonical case
    unextractable.
    """
    assert parse_bound("2026-02") == datetime(2026, 2, 1, tzinfo=timezone.utc)


def test_a_year_resolves_to_its_first_instant():
    assert parse_bound("2019") == datetime(2019, 1, 1, tzinfo=timezone.utc)


def test_prose_is_refused_rather_than_interpreted():
    """The failure mode this field introduces, and the whole reason for a parser.

    "For years" is not a date. A model that answers it with 2019 has invented
    something no one said, and nothing downstream could tell that from a fact.
    """
    for text in ("for years", "last February", "three years ago", "when I moved", ""):
        assert parse_bound(text) is None, text


def test_a_date_that_does_not_exist_is_refused():
    assert parse_bound("2026-02-30") is None
    assert parse_bound("2026-13-01") is None


def test_a_year_outside_living_memory_is_refused():
    """A hallucinated 9999 would collide with the open sentinel.

    Which would turn an invented date into a claim that the fact is still true —
    the one failure that spreads rather than sits.
    """
    assert parse_bound("9999-12-31") is None
    assert parse_bound("0001-01-01") is None


def test_anything_that_is_not_a_string_is_refused():
    assert parse_bound(None) is None
    assert parse_bound(2019) is None


def claim(tense, since=None, until=None):
    return {"tense": tense, "since": since, "until": until}


def test_tense_decides_the_end_when_no_date_was_given():
    """The behaviour every existing row has, unchanged."""
    assert _interval(claim("current")).end == OPEN_ENDED
    assert _interval(claim("past")).end is None
    assert _interval(claim("unknown")).end is None


def test_a_stated_end_beats_the_tense():
    """ "She is CTO until March" is not a contradiction, it is an ordinary claim."""
    interval = _interval(claim("current", until="2026-03"))

    assert interval.end == datetime(2026, 3, 1, tzinfo=timezone.utc)
    assert not interval.is_open


def test_a_start_arrives_only_from_a_date():
    """Nothing about a tense implies a beginning, which is why this was always null."""
    assert _interval(claim("current")).start is None
    assert _interval(claim("current", since="2019")).start == datetime(
        2019, 1, 1, tzinfo=timezone.utc
    )


def test_an_end_before_its_start_loses_both_bounds():
    """Evidence the model was guessing, so neither half is trusted.

    Swapping them would invent a claim nobody made. Dropping keeps the triple,
    which is still worth having and is what every row today looks like.
    """
    interval = _interval(claim("past", since="2020", until="2019"))

    assert interval.start is None
    assert interval.end is None


def test_an_unreadable_date_leaves_the_claim_no_worse_off():
    """A bad bound is not a reason to lose the relationship it was attached to."""
    interval = _interval(claim("current", since="for years"))

    assert interval.start is None
    assert interval.end == OPEN_ENDED
