"""The memory graph's temporal columns must mean what the model says they mean.

Three states share two columns here — a known timestamp, an open bound, and an
unknown one — and two of the three are represented by values rather than by
structure. That is cheap and it is only safe while the values behave: an open
bound has to survive the round trip unchanged, compare later than everything
else, and stay distinguishable from unknown.

None of that is guaranteed by the schema, and the failure mode is quiet. The
obvious "improvement" is to store `'infinity'::timestamptz`, which Postgres
accepts and psycopg 3 refuses to read back — so the write succeeds, the row is
correct in SQL, and every Python caller that selects it raises `DataError`. That
would not surface until the first open-ended fact was read, which is the first
time anyone says "she *is* their CTO".

These run against real Postgres, and have to: the whole question is what the
driver and the database do with these values, which no in-memory substitute can
answer. Start it with `just db-up`.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from bacteria.app.graph.models import ALWAYS, OPEN_ENDED


def test_the_open_bound_is_not_postgres_infinity():
    """`OPEN_ENDED` must be a real datetime, because `'infinity'` cannot be read.

    A guard against reintroducing a value that looks more correct and breaks on
    the way out. If someone replaces the sentinel with a string, this fails here
    rather than in whatever route first selects an open-ended assertion.
    """
    assert isinstance(OPEN_ENDED, datetime)
    assert isinstance(ALWAYS, datetime)
    assert OPEN_ENDED.tzinfo is not None, "a naive sentinel compares as local time"
    assert ALWAYS.tzinfo is not None


async def test_the_sentinels_survive_the_database_unchanged(engine):
    """A bound written as open must read back as open, not as something near it.

    If the round trip loses microseconds, or the driver clamps the value, then
    `valid_to == OPEN_ENDED` stops identifying open-ended facts and every such
    fact silently becomes one with a very distant end date. Nothing else would
    report that; queries would keep working and mean something different.
    """
    async with engine.connect() as db:
        for sentinel in (OPEN_ENDED, ALWAYS):
            returned = (
                await db.execute(text("SELECT CAST(:v AS timestamptz)"), {"v": sentinel})
            ).scalar_one()
            assert returned == sentinel


async def test_an_open_bound_orders_after_every_real_timestamp(engine):
    """Open must be the maximum, or "still true" sorts into the middle of history.

    The overlap test asks whether one interval ends before another begins, which
    is a comparison. An open bound that did not compare greatest would make a
    current fact look expired and a contradiction between two current claims
    undetectable.
    """
    async with engine.connect() as db:
        later, earlier = (
            await db.execute(
                text("SELECT CAST(:o AS timestamptz) > now(), CAST(:a AS timestamptz) < now()"),
                {"o": OPEN_ENDED, "a": ALWAYS},
            )
        ).one()
        assert later and earlier

        # A century out is still comfortably below the sentinel, so a real date
        # nobody would call "open" cannot be mistaken for one by ordering.
        distant = datetime.now(timezone.utc) + timedelta(days=365 * 100)
        assert (
            await db.execute(
                text("SELECT CAST(:o AS timestamptz) > CAST(:d AS timestamptz)"),
                {"o": OPEN_ENDED, "d": distant},
            )
        ).scalar_one()


async def test_an_unknown_bound_compares_as_unknown_rather_than_false(engine):
    """`NULL` has to make a comparison undecidable, which is the third state.

    Constraint evaluation has three answers — satisfied, violated, and *cannot be
    determined because a bound is unknown* — and it gets the third from SQL's own
    null semantics rather than from an extra column. If a null bound ever
    compared as `false` instead of unknown, "we do not know whether these
    conflict" would silently become "they do not conflict", which is the more
    dangerous of the two wrong answers: it hides a contradiction instead of
    showing a spurious one.
    """
    async with engine.connect() as db:
        assert (await db.execute(text("SELECT (NULL::timestamptz <= now()) IS NULL"))).scalar_one()
        assert (
            await db.execute(text("SELECT (NULL::timestamptz <= now()) IS NOT FALSE"))
        ).scalar_one()
