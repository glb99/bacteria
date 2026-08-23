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


@dataclass(frozen=True)
class FunctionalConstraint:
    """At most one ``dst`` per ``(user_id, src)`` for this relation, at a time.

    ``sentence`` is not documentation. A constraint here is a *hypothesis about
    the user's world* rather than a rule the system is entitled to enforce, so a
    person has to be able to read it and disagree — and a rule that cannot be
    said in one sentence cannot be argued with. It is a field so that the
    sentence travels with the rule to wherever the disagreement happens.
    """

    rel: str
    sentence: str

    def conflicts(
        self,
        assertions: Iterable[Assertion],
        *,
        conclusions: Sequence[Conclusion] = (),
    ) -> list[Conflict]:
        """Every pair of believed claims this rule says cannot both hold.

        Takes the claims *already* narrowed to one moment — usually
        :func:`~bacteria.app.graph.log.state_at`. Doing the narrowing here would
        hide which moment is being asked about, and "is there a conflict" has a
        different answer at every point in both time axes.

        Pairs are compared within a ``(user_id, src)`` group, so one person's
        graph can never produce a conflict against another's. That is a
        correctness property before it is a privacy one, but it is both.
        """
        relevant = [a for a in assertions if a.rel == self.rel]
        grouped: dict[tuple[str, str], list[Assertion]] = {}
        for assertion in relevant:
            grouped.setdefault((assertion.user_id, assertion.src), []).append(assertion)

        found: list[Conflict] = []
        for group in grouped.values():
            for index, left in enumerate(group):
                for right in group[index + 1 :]:
                    if left.dst == right.dst:
                        continue
                    state = self._state(left, right, conclusions)
                    if state is not None:
                        found.append(
                            Conflict(self.rel, left.assertion_id, right.assertion_id, state)
                        )
        return found

    def _state(
        self, left: Assertion, right: Assertion, conclusions: Sequence[Conclusion]
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


SEEDED: tuple[FunctionalConstraint, ...] = (
    FunctionalConstraint(rel="cto", sentence="An organization has one CTO at a time."),
    FunctionalConstraint(rel="ceo", sentence="An organization has one CEO at a time."),
    FunctionalConstraint(rel="employer", sentence="A person has one employer at a time."),
)
"""The constraints that exist, which is a hardcoded three.

Not built:
    Anywhere for a constraint to come from. Nobody authors these: a person will
    not sit down and write functional properties, and the model is explicit that
    they should never have to. The agent proposing them from observed regularity
    is the obvious answer and is not obviously right — a wrongly inferred
    constraint generates false contradictions *forever*, which is worse than
    having no constraint at all, and there is no equivalent of the rule of three
    to say when a regularity is an invariant rather than a coincidence.

    Left as a literal until that question has an answer, because a table and an
    authoring route would commit to one before anyone chose it. Three is enough
    to exercise the layer and small enough that a wrong one is noticed. When it
    moves, it moves to rows keyed by owner, since "a person has one employer" is
    exactly the kind of rule a particular person is entitled to disagree with.
"""
