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


_MONTHS = (
    # Longest first, so the alternation cannot match a prefix and stop.
    "january",
    "february",
    "march",
    "april",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
    "sept",
    "jan",
    "feb",
    "mar",
    "apr",
    "may",
    "jun",
    "jul",
    "aug",
    "sep",
    "oct",
    "nov",
    "dec",
)

_DATE_IN_PROSE = re.compile(
    r"\b(?:" + "|".join(_MONTHS) + r")\b|\b(?:19|20)\d{2}\b|\b\d{1,2}/\d{1,2}\b",
    re.IGNORECASE,
)
"""A month, a plausible year, or a numeric day/month.

**Whole words, and the first version was not.** Matching month *prefixes* —
``mar\\w*`` — made "Marta took over as CTO" carry a date, because the successor's
name begins with one. The one example this guard exists for defeated it, and a
test written from that example is what said so.

"May" remains genuinely ambiguous with a name and is kept, because a reason that
says only "May" and licenses a bound is rarer than one that means the month.
"""


def stated_in(reason: object) -> bool:
    """Do the words supporting a claim contain a date at all?

    **The guard that stops an inferred boundary entering the log as a fact.** The
    first real conversation after dates were added produced this pair:

    ==============================  =================  =======
    reason                          bound              stated
    ==============================  =================  =======
    "Diane left Acme in Feb 2026"   ``until 2026-02``  yes
    "Marta took over as CTO"        ``since 2026-02``  **no**
    ==============================  =================  =======

    Nobody said when Marta started. The model worked it out — from exactly the
    reasoning :func:`~bacteria.app.graph.inference.infer_succession` exists to
    perform, and having been told in the prompt not to.

    That matters more than a merely wrong date would. When the engine infers a
    boundary it writes a *conclusion*: confidence 0.6, evidence on both premises,
    withdrawn when either moves. When the model infers one it writes an
    **assertion**, indistinguishable from something observed — an assumed value
    entering the log through a side door. And it conceals itself, because
    supplying the boundary removes the precondition the engine needed in order to
    propose it properly: the better the model gets at guessing, the less the
    defeasible machinery ever runs.

    So the check is on the *supporting words*, which the model quotes rather than
    composes. Presence, not agreement: a reason mentioning any date licenses the
    bounds on that claim, and a reason mentioning none licenses nothing.

    Not built:
        Agreement between the words and the value. A reason saying "in 2019"
        licenses a bound of ``2024-03``, and one date in the words licenses both
        a ``since`` and an ``until``. The failure seen in practice is a reason
        with *no* date, and a stricter check would start refusing paraphrases —
        this field is "quoted or closely paraphrased", not a quotation.

        Months in any language but English. A Spanish reason carrying "febrero"
        and no year loses its bound. That is under-claiming, the recoverable
        direction, and the alternative is a list of languages with no principled
        end.
    """
    return isinstance(reason, str) and _DATE_IN_PROSE.search(reason) is not None
