"""Beliefs the system drew rather than was told, and what happens when their
evidence moves.

A conclusion is not a memory. Nothing here reaches a model: accepting one writes
an ordinary memory entry carrying its prose, which is what a human confirmed, and
that is the agent's ADR 0017 boundary rather than a convention of this package.

**Evidence links are mandatory, and the reason is one operation.** When an
assertion is revised, every conclusion that leaned on it has to be found and
marked — which is a lookup *backwards*, from an assertion to its dependents.
Without it this layer is an audit log; with it the memory notices when it has
gone out of date. :func:`stale_after` is that walk.

**Stale is not wrong.** A conclusion drawn last week from what was known last
week was a correct inference from a premise that has since moved. Marking it
``stale`` says the support went, not that the reasoning did — and keeping those
distinguishable is why conclusions carry a status rather than being deleted.
"""

from dataclasses import dataclass, replace
from datetime import datetime
from typing import Iterable, Literal, Sequence

ConclusionStatus = Literal["active", "stale", "superseded", "retracted"]
"""Where a conclusion is in its life.

``stale`` is the state that justifies this module existing — see
:func:`stale_after`. ``superseded`` and ``retracted`` are terminal and differ in
who ended it: a later conclusion replaced this one, or someone decided it was
never sound.
"""

DerivedBy = Literal["llm-judgment", "constraint-inference"]
"""What produced a conclusion, and the distinction is not human-versus-machine.

A deterministic rule can still be **defeasible**: "she became CTO when he left"
follows from a constraint and one known boundary, and the same data is equally
consistent with a gap in which nobody held the role. Entailed things are derived
properties and get recomputed silently; assumed things are conclusions, carry
evidence, and can be retracted.
"""


@dataclass(frozen=True)
class Conclusion:
    """A belief, with the assertions it rests on.

    ``evidence`` holds assertion ids rather than assertions, because it is a
    reference to a *version* of a claim and not to the claim's current shape. An
    assertion is never edited, so the id keeps pointing at what was actually
    used — which is the property that makes :func:`stale_after` meaningful and
    that a foreign key to a current-state row could not provide.

    Frozen for the same reason assertions are: a status change produces a new
    value through :func:`stale_after`, so nothing changes a belief in place while
    something else is reading it.
    """

    conclusion_id: str
    user_id: str
    statement: str
    evidence: tuple[str, ...]
    confidence: float
    derived_by: DerivedBy
    recorded_at: datetime
    status: ConclusionStatus = "active"


def stale_after(conclusions: Iterable[Conclusion], revised: Sequence[str]) -> list[Conclusion]:
    """Mark every active conclusion that cited a revised assertion.

    Returns the *changed* conclusions only, so a caller writes what moved rather
    than rewriting the set. An empty result means the revision supported nothing,
    which is the common case and should cost nothing to discover.

    Only ``active`` conclusions are touched. Re-staling an already stale one
    would rewrite a row to the value it holds, and reviving a ``retracted`` one
    because its evidence changed would resurrect a belief somebody killed.

    Deliberately not recursive. A conclusion citing another conclusion would need
    the walk to continue through it, and nothing builds those yet — see the gap
    below rather than assuming this handles it.

    Not built:
        Conclusions as evidence for other conclusions. The chain is real — a
        belief drawn from a belief — and this walk stops at the first level, so a
        second-order conclusion would keep an ``active`` status after its
        grounds went stale. It is unbuilt because nothing produces one, and the
        fix belongs here, as a transitive closure over evidence that is a
        conclusion id rather than an assertion id.
    """
    revised_ids = set(revised)
    return [
        replace(c, status="stale")
        for c in conclusions
        if c.status == "active" and revised_ids.intersection(c.evidence)
    ]
