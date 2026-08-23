"""When a claim was true, and whether two of them can have been true at once.

The one question this module answers is ``overlaps``, and it has **three**
answers rather than two. That is the whole reason it exists as its own module:
a comparison that can return "cannot be determined" is not a predicate, and
callers that treat it as one silently turn "we do not know whether these
conflict" into "they do not conflict" — the more dangerous of the two wrong
answers, because it hides a contradiction rather than showing a spurious one.

**A bound has three states.** A timestamp is a known moment. :data:`OPEN_ENDED`
(or :data:`ALWAYS`, its mirror) says the interval genuinely has no end: the claim
is true as of now and continuing. ``None`` says nobody knows.

Open and unknown look alike and are not. "She is their CTO" and "she was
mentioned as CTO" differ in exactly this, and only the first says the claim still
holds. Collapsing them is the mistake the three states exist to prevent, and it
is easy to make because prose writes both as a blank.

Nothing here touches the database or the ORM. It is called by
:mod:`bacteria.app.graph.constraints`, and it is tested with plain values.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

OPEN_ENDED = datetime.max.replace(tzinfo=timezone.utc)
"""Valid time that has not ended: true as of now, and continuing.

A sentinel rather than ``'infinity'``, and this was measured rather than
reasoned about. Postgres accepts ``'infinity'::timestamptz`` and **psycopg 3
raises on the way back**: ``DataError: timestamp too large (after year 10K)``. It
does not degrade to ``datetime.max``; it refuses. A row carrying it would be
writable, correct in SQL, and fatal to every Python caller that selected it —
and nothing would notice until the first open-ended fact was read.

``datetime.max`` was checked against this stack instead: it round-trips to the
same value, compares greater than ``now()``, and orders correctly, so indexes and
``ORDER BY`` behave. ``tests/test_graph_models.py`` is what keeps that true.

Being the maximum is also load-bearing *here*, not only in SQL: it makes
:func:`overlaps` treat an open interval as extending past every real timestamp
without a special case in the comparison itself.

What it costs: a fact genuinely valid until the year 9999 is indistinguishable
from an open one. Every query anyone will write treats those identically, which
is why this is acceptable rather than merely tolerated.

Distinct from ``None``, which means *unknown*.
"""

ALWAYS = datetime.min.replace(tzinfo=timezone.utc)
"""Valid time with no beginning: true for as long as the subject existed.

The mirror of :data:`OPEN_ENDED` and much rarer — most facts started at some
unrecorded moment, which is ``None``, not this. Reach for it only when "has
always been true" is a claim someone actually made.
"""


@dataclass(frozen=True)
class Interval:
    """When a claim held in the world.

    Frozen, because an assertion is never edited: revising a fact appends a new
    one. An interval that could be mutated in place would make that guarantee a
    convention rather than a property.

    Both bounds default to unknown, which is the honest default — most facts
    arrive without dates attached, and a default of "open" would silently claim
    every extracted fact is still true.
    """

    start: Optional[datetime] = None
    end: Optional[datetime] = None

    @property
    def is_open(self) -> bool:
        """True when the claim is asserted to still hold, rather than merely undated."""
        return self.end == OPEN_ENDED


def overlaps(a: Interval, b: Interval) -> Optional[bool]:
    """Could these two claims have been true at the same moment?

    Returns ``True`` when they provably overlap, ``False`` when they provably do
    not, and ``None`` when an unknown bound makes it undecidable. Callers must
    handle all three; ``if overlaps(a, b):`` treats undecidable as "no", which is
    the bug this signature exists to make visible.

    Two open-ended intervals always overlap, whatever their starts, because both
    are asserted to be true *now* and therefore share the present moment. That
    case is checked first and is not an optimization: with both starts unknown
    the general rule below would answer ``None``, and "we cannot tell whether two
    people are both currently the CTO" is wrong — we can.

    Everything else falls out of the sentinels being extreme values. An open end
    is the maximum, so it never sorts before another interval's start; ``ALWAYS``
    is the minimum, so nothing ends before it. Neither needs a branch.
    """
    if a.is_open and b.is_open:
        return True

    if _ends_before(a, b) or _ends_before(b, a):
        return False

    # Not provably apart, and still not provably together: an unknown bound
    # could put them either way.
    if None in (a.start, a.end, b.start, b.end):
        return None

    return True


def _ends_before(x: Interval, y: Interval) -> bool:
    """Does ``x`` provably finish at or before ``y`` starts?

    Deliberately conservative: an unknown bound on either side means *not
    proven*, never *false*. The caller distinguishes those two, and folding them
    together here is how "undecidable" would quietly become "no conflict".
    """
    if x.end is None or y.start is None:
        return False
    return x.end <= y.start
