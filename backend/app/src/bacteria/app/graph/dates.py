"""Turning a date a transcript stated into a bound, and refusing the rest.

`valid_from` was null on every row the extractor ever wrote, and `valid_to` was
either the open sentinel or null. Not because the model got it wrong — it was
asked for a *tense* and answered correctly fifteen times out of fifteen — but
because nothing ever asked for a date. So the second time axis was carrying one
state out of three, and succession inference, which needs a boundary to hand a
successor, had nothing it could ever fire on.

**A model asked for a date will produce one.** That is the whole difficulty. "I've
worked there for years" becomes an invented 2019, and an invented start is worse
than no start: it is checkable-looking and wrong, where a null is honestly
ignorant. Every rule here therefore errs toward refusing, which is the
recoverable direction and the same one ``past`` and ``unknown`` already collapse
in.

**Partial dates are accepted and that is a real concession.** ADR 0006's worked
example is *"she left in February"* — the canonical case the whole temporal layer
was designed around — and February is not a full date. Requiring one would have
made the design's own example unextractable. So a month resolves to its first
instant, and the text the model was reading is kept beside it, because the
resolution is a decision this module made rather than something anyone said.

Not built:
    Relative dates. "Last February", "three years ago" and "when I moved" are how
    people actually speak, and resolving them needs to know what *now* was for
    that turn. The prompt cannot carry today's date: ``PROMPT_VERSION`` is a hash
    of the prompt text and would churn daily, destroying the one key retraction
    has. Anchoring belongs in the rendered transcript instead, and until it is
    there these are refused rather than guessed.

    Precision as a value. A bound resolved from "2019" and one stated as
    "2019-03-04" are the same ``timestamptz`` and nothing downstream can tell
    them apart. The raw text in ``attrs`` makes it recoverable by reading and not
    by querying, which is enough while nothing queries it.
"""

import re
from datetime import datetime, timezone
from typing import Optional

_EARLIEST = 1900
_LATEST = 2100
"""The range a stated date may fall in.

Not validation for its own sake. A model that has decided to invent one tends to
invent something wild — a year 0001 or 9999 — and the second collides with the
open sentinel, which would turn a hallucinated date into a claim that a fact is
still true.
"""

_PATTERNS = (
    (re.compile(r"^(\d{4})-(\d{2})-(\d{2})$"), 3),
    (re.compile(r"^(\d{4})-(\d{2})$"), 2),
    (re.compile(r"^(\d{4})$"), 1),
)


def parse_bound(text: object) -> Optional[datetime]:
    """A stated date as an instant, or ``None`` if it is not one.

    Accepts ``YYYY``, ``YYYY-MM`` and ``YYYY-MM-DD``, and resolves a partial one
    to the **first** instant of the period it names. First rather than last
    because a bound is read at both ends: as a start, "she joined in 2019" is
    earliest-consistent at January; as an end it means the same fact stopped
    holding somewhere in that period, and taking the earliest under-claims how
    long it held. Under-claiming is the direction that stays recoverable.

    Rejects rather than repairs. A trailing word, a slash, a month of 13, a year
    outside living memory: all ``None``. The caller records the claim without the
    bound, which is exactly the state every row is in today.
    """
    if not isinstance(text, str):
        return None

    candidate = text.strip()
    for pattern, parts in _PATTERNS:
        match = pattern.match(candidate)
        if match is None:
            continue
        year = int(match.group(1))
        if not _EARLIEST <= year <= _LATEST:
            return None
        month = int(match.group(2)) if parts >= 2 else 1
        day = int(match.group(3)) if parts >= 3 else 1
        try:
            return datetime(year, month, day, tzinfo=timezone.utc)
        except ValueError:
            # A real date that does not exist -- 2026-02-30, 2026-13-01. The
            # regex cannot see this and the constructor can.
            return None
    return None
