"""Rules about what cannot be true at once, and what to do when we cannot tell.

One construct so far: a **functional** relation, where a subject may have at most
one object at any one moment. "An organization has one CTO" is the shape, and it
is enough to exercise everything the layer needs — a rule, a violation, and the
case in between.

**A conflict is a state, not an error.** Two claims that contradict each other
both land, keep their provenance, and the disagreement becomes something to look
at. A system modelling a person's world has to be able to say that world is
currently inconsistent, because it often is, and because resolving it
automatically means picking one and being wrong about half the time.

**There are four states, and the interesting one is third.** Because
:func:`~bacteria.app.graph.temporal.overlaps` can answer "cannot be determined",
a violation can be undecidable — two claims that would conflict if their dates
overlapped, where the dates are unknown. That is *possible*, and it is reported
rather than rounded to either neighbour. A possible conflict with a conclusion
accounting for it is *explained*: still undecided, but no longer unattended.

Nothing here rejects a write. That is the point: this reports, and the review
surface decides what a person is shown.
"""

from dataclasses import dataclass
from typing import Iterable, Literal, Sequence

from bacteria.app.graph.catalogue import Relation
from bacteria.app.graph.conclusions import Conclusion
from bacteria.app.graph.log import Assertion
from bacteria.app.graph.temporal import overlaps

ConflictState = Literal["conflict", "possible", "explained"]
"""How sure we are that two claims collide.

``conflict`` is provable from the dates. ``possible`` means an unknown bound
leaves it open. ``explained`` is ``possible`` plus an active conclusion that
accounts for it — see :mod:`bacteria.app.graph.inference`.

There is no ``none``: agreement is the absence of a :class:`Conflict`, not a kind
of one, and giving it a name would invite callers to filter a list instead of
checking whether it is empty.
"""


@dataclass(frozen=True)
class Conflict:
    """Two assertions that a constraint says cannot both hold.

    Carries assertion ids rather than assertions because that is what everything
    downstream needs — rendering a badge, citing evidence, resolving it later —
    and because holding the values would make a conflict a snapshot that goes
    quietly out of date.
    """

    rule: str
    left: str
    right: str
    state: ConflictState


def conflicts_for(
    relation: Relation,
    assertions: Iterable[Assertion],
    *,
    conclusions: Sequence[Conclusion] = (),
) -> list[Conflict]:
    """Every pair of believed claims this relation says cannot both hold.

    A free function over a :class:`~bacteria.app.graph.catalogue.Relation` rather
    than a method on a constraint object, because there is no constraint object
    any more: being functional is a property of a relation, and the rule and the
    vocabulary entry were always the same fact stated twice.

    Returns nothing for a relation that is not functional, which keeps the caller
    from having to ask first.

    Takes the claims *already* narrowed to one moment — usually
    :func:`~bacteria.app.graph.log.state_at`. Doing the narrowing here would hide
    which moment is being asked about, and "is there a conflict" has a different
    answer at every point in both time axes.

    Pairs are compared within a ``(user_id, src)`` group, so one person's graph
    can never produce a conflict against another's. That is a correctness
    property before it is a privacy one, but it is both.
    """
    if not relation.functional:
        return []

    relevant = [a for a in assertions if a.rel == relation.name]
    grouped: dict[tuple[str, str], list[Assertion]] = {}
    for assertion in relevant:
        grouped.setdefault((assertion.user_id, assertion.src), []).append(assertion)

    found: list[Conflict] = []
    for group in grouped.values():
        for index, left in enumerate(group):
            for right in group[index + 1 :]:
                if left.dst == right.dst:
                    continue
                state = _state(left, right, conclusions)
                if state is not None:
                    found.append(
                        Conflict(relation.name, left.assertion_id, right.assertion_id, state)
                    )
    return found


def _state(
    left: Assertion, right: Assertion, conclusions: Sequence[Conclusion]
) -> ConflictState | None:
    """Classify one pair, or ``None`` when the dates prove there is no clash."""
    verdict = overlaps(left.valid, right.valid)
    if verdict is False:
        return None
    if verdict is True:
        return "conflict"
    return "explained" if _explained(left, right, conclusions) else "possible"


def _explained(left: Assertion, right: Assertion, conclusions: Sequence[Conclusion]) -> bool:
    """Is there a live conclusion accounting for this particular pair?

    Both ids must appear in one conclusion's evidence. A conclusion about only
    one of them explains something else, and matching on either would let an
    unrelated inference silently quiet a conflict it never considered.

    Retracted and stale conclusions do not count. That is what makes the
    explanation defeasible in practice: withdraw the assumption and the conflict
    returns to ``possible``, which is the honest state it was in before anyone
    assumed anything.
    """
    pair = {left.assertion_id, right.assertion_id}
    return any(
        c.status == "active" and c.derived_by == "constraint-inference" and pair <= set(c.evidence)
        for c in conclusions
    )
