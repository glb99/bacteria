"""Filling in a boundary a constraint implies, without pretending it was observed.

When one role ends in February and another has no recorded start, a person
concludes instantly that the second began when the first ended. The inference is
worth making — without it every succession stays permanently undecided, and a
badge that is always lit is a badge nobody reads.

**It is a conclusion, not a derived property, and the distinction is not who
computed it.** This rule is fully deterministic and still not entailed: the same
data is equally consistent with a gap in which nobody held the role, or a
handover during which both did. Entailed things are recomputed silently; assumed
things carry evidence and can be withdrawn.

**The assumed date is never written onto an assertion.** That was tried, in a
prototype, and it was wrong in a way worth recording because the code looked
better: writing the boundary made the two intervals provably apart, so the
conflict *disappeared* instead of becoming explained — the assumption vanished
from view at exactly the moment it started carrying weight, and the next
inference would have read a guess as an observation. Keeping it here, in the
conclusion, makes compounding structurally impossible rather than something a
guard has to catch, and leaves retraction with nothing to un-write.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Optional, Sequence

from bacteria.app.graph.catalogue import Relation
from bacteria.app.graph.conclusions import Conclusion
from bacteria.app.graph.log import Assertion
from bacteria.app.graph.temporal import OPEN_ENDED, Interval, overlaps

SUCCESSION_CONFIDENCE = 0.6
"""How much to trust "the next one started when the last one ended".

Not high, and deliberately so. The rule is right often enough to be worth making
and wrong often enough — vacancies, overlapping handovers, a source that was
simply mistaken — that a person should see it as a suggestion carrying a number
rather than as something the system knows.
"""


@dataclass(frozen=True)
class Succession:
    """A proposed boundary, and the two claims it sits between.

    Returned instead of a bare :class:`Conclusion` so a caller can render the
    inferred date without it having been written anywhere. ``boundary`` is the
    assumption; nothing in the log says it.
    """

    conclusion: Conclusion
    predecessor: str
    successor: str
    boundary: datetime


def infer_succession(
    assertions: Iterable[Assertion],
    relation: Relation,
    *,
    conclusion_id: str,
    now: datetime,
) -> Optional[Succession]:
    """Propose that an undated claim began when the dated one it displaces ended.

    Returns ``None`` whenever the situation is not unambiguous, which is most of
    the time. Three guardrails, each rejecting a case where the inference would
    be a guess dressed as a deduction:

    - **Exactly one claim has ended.** Two ended roles and one open successor
      gives no way to say which the successor follows.
    - **Exactly one claim is open with an unknown start.** Two candidates means
      choosing, and there is nothing here to choose with.
    - **Nothing else spans the boundary.** A third holder covering the moment
      means the succession is not direct, so the implied date is wrong even
      though the arithmetic works.

    A fourth guard is absent because the design removed the need for it: the
    predecessor's end can never be an inferred value, since inferred values are
    not written to assertions at all. That is the point of returning a
    :class:`Succession` rather than an edited claim.
    """
    believed = [a for a in assertions if a.rel == relation.name and a.recorded_until is None]
    if not believed:
        return None

    ended = [a for a in believed if _has_known_end(a)]
    open_undated = [a for a in believed if a.valid.is_open and a.valid.start is None]
    if len(ended) != 1 or len(open_undated) != 1:
        return None

    predecessor, successor = ended[0], open_undated[0]
    if predecessor.dst == successor.dst:
        return None
    if predecessor.user_id != successor.user_id or predecessor.src != successor.src:
        return None

    boundary = predecessor.valid.end
    if boundary is None:
        # Unreachable: `_has_known_end` already established it. Written as a
        # return rather than an assert because a type checker cannot see through
        # the helper, and an assert would vanish under `python -O`.
        return None
    if _someone_else_spans(believed, boundary, {predecessor.assertion_id, successor.assertion_id}):
        return None

    conclusion = Conclusion(
        conclusion_id=conclusion_id,
        user_id=successor.user_id,
        statement=(
            f"{successor.dst} took over {relation.name} of {successor.src} "
            f"on {boundary.date().isoformat()}, when {predecessor.dst}'s tenure ended"
        ),
        # Assertion ids only. The rule that licensed this is named in the
        # statement rather than cited here, because evidence is a foreign key to
        # the assertion log and the rule is a flag on a catalogue entry — there is
        # no row for it to point at. If the catalogue ever becomes rows, this is
        # where the third id goes.
        evidence=(predecessor.assertion_id, successor.assertion_id),
        confidence=SUCCESSION_CONFIDENCE,
        derived_by="constraint-inference",
        recorded_at=now,
    )
    return Succession(conclusion, predecessor.assertion_id, successor.assertion_id, boundary)


def _has_known_end(assertion: Assertion) -> bool:
    """An end that is a real date — neither unknown nor the open sentinel."""
    end = assertion.valid.end
    return end is not None and end != OPEN_ENDED


def _someone_else_spans(believed: Sequence[Assertion], boundary: datetime, pair: set[str]) -> bool:
    """Does a third claim cover the moment the handover supposedly happened?

    Uses the same overlap rule as everything else, against a zero-width interval
    at the boundary, so "spans" means what it means everywhere. An *undecidable*
    answer counts as spanning: the guard exists to refuse ambiguous cases, and
    treating "cannot tell" as "does not span" would let it through exactly when
    the evidence is weakest.
    """
    instant = Interval(boundary, boundary)
    return any(
        overlaps(other.valid, instant) is not False
        for other in believed
        if other.assertion_id not in pair
    )
