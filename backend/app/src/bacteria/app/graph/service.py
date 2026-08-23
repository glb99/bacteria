"""What happens when the graph learns something, and when it learns it was wrong.

Composes the two halves of this package: the repository, which knows storage and
nothing else, and the engine, which knows the rules and has never seen a
database. Neither imports the other. This is the only module that knows the
order they go in.

Two operations, and they are the two things that ever happen to a memory:
something is **observed**, or something already believed is **revised**.

Both return a description of what changed rather than raising. Learning a fact
that contradicts another is not an error — it is the case this system exists to
represent — so a caller gets told what it now knows and decides what a person
sees. That split is the one ``chat/review.py`` makes and for the same reason:
the surfaces turn outcomes into a response body or a line of terminal output,
and a decision made in an entrypoint is a decision nothing tests.

**Nothing here reaches a model.** Assertions land, conflicts are reported and
conclusions are recorded, and none of it contributes text to a prompt. What a
person confirms becomes an ordinary memory entry through the existing review
path — the agent's ADR 0017 boundary, unchanged by any of this.
"""

import uuid
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Sequence

from bacteria.app.graph.conclusions import Conclusion, stale_after
from bacteria.app.graph.constraints import SEEDED, Conflict, FunctionalConstraint
from bacteria.app.graph.identity import Node
from bacteria.app.graph.inference import infer_succession
from bacteria.app.graph.log import Assertion
from bacteria.app.graph.repository import SqlGraphRepository


@dataclass(frozen=True)
class Outcome:
    """What changed, and what a person might need to look at.

    ``conflicts`` is every disagreement the affected rules can see *after* the
    write, not only ones this write caused. A caller rendering a badge needs the
    current state of the world rather than a delta, and computing the delta would
    mean holding the previous state to subtract it from — which is the projection
    this package deliberately does not cache.

    ``inferred`` and ``stale`` are genuinely deltas: they are things that just
    happened and would otherwise have to be discovered by polling.
    """

    conflicts: list[Conflict] = field(default_factory=list)
    inferred: list[Conclusion] = field(default_factory=list)
    stale: list[Conclusion] = field(default_factory=list)

    @property
    def needs_attention(self) -> bool:
        """Is there anything here a person would want to know about?

        A provable conflict or a belief that lost its support. A *possible*
        conflict deliberately does not count: undated claims are the normal case,
        and treating every one as something to review is how a queue becomes
        noise nobody reads.
        """
        return any(c.state == "conflict" for c in self.conflicts) or bool(self.stale)


async def refer_to(
    repository: SqlGraphRepository, user_id: str, kind: str, label: str, *, now: datetime
) -> Node:
    """The node this name refers to, creating one the first time it is heard.

    The only way an assertion should acquire a node id. Callers that mint their
    own would each decide separately when two mentions are the same thing, and
    "which Diane" would be answered differently by the extractor and the review
    surface.

    Exact match on a normalized name, and nothing cleverer — see
    :mod:`bacteria.app.graph.identity` for why the conservative direction is the
    safe one. Splitting a person across two nodes is fixed later by asserting a
    link; collapsing two people into one is not fixable at all.

    ``last_seen`` moves on every mention, including the first, so a node that has
    only ever been mentioned once still says when.
    """
    existing = await repository.node_named(user_id, kind, label)
    if existing is None:
        return await repository.mint_node(user_id, kind, label, now=now)
    await repository.touch_node(user_id, existing.node_id, now=now)
    # Rebuilt rather than returned as read: `existing` was loaded before the
    # touch and still carries the old `last_seen`. Handing that back would give a
    # caller a value that disagrees with the row it names, which is the class of
    # bug the detached-reads rule exists to prevent and which this reintroduced
    # by updating after reading.
    return replace(existing, last_seen=now)


async def observe(
    repository: SqlGraphRepository,
    assertions: Sequence[Assertion],
    *,
    now: datetime,
    constraints: Sequence[FunctionalConstraint] = SEEDED,
) -> Outcome:
    """Record claims, then say what they collide with.

    The order matters and is the reason this module exists: the claims are
    written *before* the rules run, so a constraint sees the world as it now is
    rather than as it was plus a pending change. Evaluating first would make a
    conflict between two assertions in the same batch invisible.

    Safe to call twice; :func:`_reconcile` says why.
    """
    if not assertions:
        return Outcome()

    await repository.record(assertions)

    owner = assertions[0].user_id
    conflicts, inferred = await _reconcile(
        repository, owner, {a.rel for a in assertions}, constraints, now
    )
    return Outcome(conflicts=conflicts, inferred=inferred)


async def revise(
    repository: SqlGraphRepository,
    closed: Assertion,
    replacement: Assertion,
    *,
    now: datetime,
    constraints: Sequence[FunctionalConstraint] = SEEDED,
) -> Outcome:
    """Correct a claim, and mark everything that had been resting on it.

    The staleness walk is the reason evidence links are mandatory, and running it
    here rather than leaving it to a caller is the reason this is a service and
    not two calls. A revision that skipped it would leave beliefs standing on
    evidence that moved, with nothing recording that they should be looked at
    again — the difference between a memory that self-corrects and one that is
    merely a log.

    Stale is not wrong. A conclusion drawn from what was known then was a sound
    inference from a premise that has since changed, and the status says the
    support went rather than that the reasoning did.
    """
    owner = closed.user_id
    dependents = await repository.depending_on(owner, [closed.assertion_id])

    await repository.supersede(closed, replacement)

    now_stale = stale_after(dependents, [closed.assertion_id])
    for conclusion in now_stale:
        await repository.set_status(owner, conclusion.conclusion_id, "stale")

    conflicts, inferred = await _reconcile(repository, owner, {replacement.rel}, constraints, now)
    return Outcome(conflicts=conflicts, inferred=inferred, stale=now_stale)


async def _reconcile(
    repository: SqlGraphRepository,
    owner: str,
    relations: set[str],
    constraints: Sequence[FunctionalConstraint],
    now: datetime,
) -> tuple[list[Conflict], list[Conclusion]]:
    """Evaluate the affected rules, explain what can be explained, evaluate again.

    Shared by both operations, and it has to be. The first version ran inference
    only from :func:`observe` and had :func:`revise` merely report — which is
    exactly backwards, because **a revision is the moment an explanation becomes
    possible**. Learning that a role ended in February is what gives the
    successor a boundary to have started at; before that there was nothing to
    infer from. A test of week 4 caught it, reporting ``possible`` where the
    whole point of the correction was to reach ``explained``.

    Inference runs only on ``possible`` conflicts, which is where idempotence
    comes from: a conflict already carrying an active explanation reads as
    ``explained`` and is skipped, so a retried job does not accumulate duplicate
    conclusions. The alternative — checking for an existing conclusion before
    inferring — is the same test written twice, in two places that can disagree.
    """
    believed = await repository.current(owner)
    conclusions = await repository.depending_on(owner, [a.assertion_id for a in believed])
    applicable = [c for c in constraints if c.rel in relations]

    conflicts: list[Conflict] = []
    inferred: list[Conclusion] = []
    for constraint in applicable:
        for conflict in constraint.conflicts(believed, conclusions=conclusions):
            if conflict.state != "possible":
                continue
            succession = infer_succession(
                believed, constraint, conclusion_id=str(uuid.uuid4()), now=now
            )
            if succession is None:
                continue
            await repository.record_conclusion(succession.conclusion)
            inferred.append(succession.conclusion)
            conclusions = [*conclusions, succession.conclusion]
        # Recomputed after inference, so a caller is told the state a person
        # would see rather than the one that held for the instant before the
        # explanation was recorded.
        conflicts.extend(constraint.conflicts(believed, conclusions=conclusions))

    return conflicts, inferred
