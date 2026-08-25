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

from bacteria.app.graph.catalogue import CATALOGUE, Relation
from bacteria.app.graph.conclusions import Conclusion, stale_after
from bacteria.app.graph.constraints import Conflict, conflicts_for
from bacteria.app.graph.identity import SELF, Node, normalize, owner_node_id
from bacteria.app.graph.inference import infer_succession
from bacteria.app.graph.log import Assertion
from bacteria.app.graph.repository import SqlGraphRepository
from bacteria.app.graph.temporal import OPEN_ENDED, Interval


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

    ``recorded`` is how many claims were written, which is not how many were
    handed in: a claim the log already believes is not written again. A caller
    reporting a count from the length of its own list would be counting its
    intentions.
    """

    recorded: int = 0
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
    if kind == "person" and normalize(label) == SELF:
        # A first-person mention is about the owner, whatever spelling reached
        # here. Routed before the lexical lookup so that "self" can never mint an
        # ordinary node and leave the owner with two.
        return await owner(repository, user_id, now=now)

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


async def owner(repository: SqlGraphRepository, user_id: str, *, now: datetime) -> Node:
    """The node standing for the person whose graph this is.

    Its id is derived from the user id rather than allocated, so this is a
    get-or-create that two concurrent first mentions cannot turn into two nodes —
    the failure that would split the owner's own assertions across a pair of
    "self" nodes with nothing recording that they are one person.

    The label starts as ``self`` because a transcript rarely names the speaker.
    It is a label like any other and can be corrected the day their name is
    learned, which is why the id does not depend on it.
    """
    node_id = owner_node_id(user_id)
    existing = await repository.node(user_id, node_id)
    if existing is None:
        return await repository.mint_node(user_id, "person", SELF, now=now, node_id=node_id)
    await repository.touch_node(user_id, node_id, now=now)
    return replace(existing, last_seen=now)


async def observe(
    repository: SqlGraphRepository,
    assertions: Sequence[Assertion],
    *,
    now: datetime,
    relations: Sequence[Relation] = CATALOGUE,
) -> Outcome:
    """Record claims, then say what they collide with.

    The order matters and is the reason this module exists: the claims are
    written *before* the rules run, so a constraint sees the world as it now is
    rather than as it was plus a pending change. Evaluating first would make a
    conflict between two assertions in the same batch invisible.

    **A claim the log already believes is not written again.** The reasons are in
    :func:`_unrepeated`; the consequence here is that ``recorded`` may be smaller
    than the batch, and that the rules still run either way — a caller asked what
    these claims collide with, and the answer does not depend on whether writing
    them was necessary.

    Safe to call twice; :func:`_reconcile` says why.
    """
    if not assertions:
        return Outcome()

    owner = assertions[0].user_id

    # Two reads of the same projection, and they are not one read used twice: this
    # one must see the world *before* the write to tell a repeat from a new claim,
    # and `_reconcile`'s must see it after, or a conflict between two claims in
    # this batch is invisible.
    believed = await repository.current(owner)
    fresh = _unassumed(_unrepeated(assertions, believed), believed)
    if fresh:
        await repository.record(fresh)

    conflicts, inferred = await _reconcile(
        repository, owner, {a.rel for a in assertions}, relations, now
    )
    return Outcome(recorded=len(fresh), conflicts=conflicts, inferred=inferred)


def _unassumed(assertions: Sequence[Assertion], believed: Sequence[Assertion]) -> list[Assertion]:
    """Take back a start the model worked out from another claim's end.

    **The signature is exact and needs no language at all**: a claim whose
    ``valid.start`` equals another believed claim's ``valid.end``, for the same
    ``(user_id, src, rel)`` and a different ``dst``, is a *succession* — and
    performing one is :func:`~bacteria.app.graph.inference.infer_succession`'s
    job, not the extractor's.

    It matters which of them does it. The engine writes a **conclusion**:
    confidence 0.6, evidence on both premises, withdrawn when either moves. The
    extractor writes an **assertion**, which is indistinguishable from something
    observed — an assumed value in the log, which the whole conclusions table
    exists to prevent.

    And the extractor doing it is self-concealing. ``infer_succession`` needs an
    open claim whose start is *unknown*; supplying the start removes its
    precondition, so the boundary lands as a fact and nothing ever proposes it as
    an assumption. Stripping the start here restores the precondition, and the
    same date arrives through the path that marks it as a guess.

    **Two earlier attempts read prose and both were talked around.** Checking the
    model's ``reason`` for a date checks its output against its own output — it
    responded by writing "[in February 2026]" into the justification. Checking the
    transcript fails too, because the date was genuinely there, attached to the
    other clause of the same sentence. Only the arithmetic is unarguable.

    **A genuinely stated start that happens to coincide is demoted**, and that is
    the accepted cost. "Diane left in February and Marta started in February" is
    two stated facts, and this turns the second into an assumption carrying the
    same date. Nothing can tell that apart from the guess, and the asymmetry
    decides it: an assumption recorded as a fact cannot be spotted afterwards,
    where a fact recorded as an assumption is visible, cited, and one confirmation
    away from being restated. ``since_said`` keeps the model's word either way.
    """
    ends: dict[tuple[str, str, str], set[datetime]] = {}
    for a in [*believed, *assertions]:
        if a.valid.end is not None and a.valid.end != OPEN_ENDED:
            ends.setdefault((a.user_id, a.src, a.rel), set()).add(a.valid.end)

    stripped: list[Assertion] = []
    for a in assertions:
        boundary = a.valid.start
        others = ends.get((a.user_id, a.src, a.rel), set())
        # `!= a.valid.end` keeps a closed claim whose own end is its own start
        # out of this: that is a zero-length interval, which is a different
        # defect and not a succession.
        if boundary is not None and boundary in others and boundary != a.valid.end:
            a = replace(a, valid=Interval(None, a.valid.end))
        stripped.append(a)
    return stripped


def _unrepeated(assertions: Sequence[Assertion], believed: Sequence[Assertion]) -> list[Assertion]:
    """The claims that say something the log does not already believe.

    **A deterministic assertion id does not give this**, and assuming it did is
    how the log filled with copies. That id is hashed from the claim *and the
    run's timestamp*, deliberately, so that a genuine second observation on a
    later day does not collide with the first — which means it collapses a
    *retried job* and never a fact mentioned again next week. Those are two
    different questions and only one of them had an answer.

    A repeat is not news about the world. Writing it appends a row saying what
    the log already says, and since every copy is believed, the projection then
    returns N identical edges for one relationship. Three "my mum" mentions in
    one afternoon produced three.

    The key is the claim and its valid interval, and both halves are deliberate:

    - **``valid`` is in it**, because the same triple over a different span is not
      a repeat. "She is their CTO" and "she was their CTO until February" are
      different claims, and collapsing them would discard the correction. What
      *should* happen there is a revision, and nothing produces one from an
      extraction yet — so today the second lands beside the first and the
      constraint layer reports it.
    - **``trust`` is not in it**, because a claim arriving through a different
      channel is news about the channel rather than about the world. The cost is
      real and worth naming: a third-party row is not upgraded when the user
      later says the same thing themselves, so the tier records the first way a
      claim arrived rather than the best. Recording a second row to carry that
      would make the log grow on provenance changes, which is not what it is a
      log of.

    Repeats *within* one batch are dropped too. The database would have collapsed
    those anyway — same instant, same id, and ``record`` ignores primary-key
    conflicts — but silently, leaving the count above claiming writes that never
    happened.
    """
    seen = {_claim_of(a) for a in believed}
    fresh: list[Assertion] = []
    for assertion in assertions:
        key = _claim_of(assertion)
        if key in seen:
            continue
        seen.add(key)
        fresh.append(assertion)
    return fresh


def _claim_of(assertion: Assertion) -> tuple[str, str, str, str, Interval]:
    """What makes two assertions the same claim, for the purpose above."""
    return (assertion.user_id, assertion.src, assertion.rel, assertion.dst, assertion.valid)


async def revise(
    repository: SqlGraphRepository,
    closed: Assertion,
    replacement: Assertion,
    *,
    now: datetime,
    relations: Sequence[Relation] = CATALOGUE,
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

    conflicts, inferred = await _reconcile(repository, owner, {replacement.rel}, relations, now)
    # One: the replacement. A revision writes unconditionally — it is a
    # correction, so the claim it states is by definition not one the log
    # already believes.
    return Outcome(recorded=1, conflicts=conflicts, inferred=inferred, stale=now_stale)


async def _reconcile(
    repository: SqlGraphRepository,
    owner: str,
    affected: set[str],
    relations: Sequence[Relation],
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
    applicable = [r for r in relations if r.name in affected]

    conflicts: list[Conflict] = []
    inferred: list[Conclusion] = []
    for relation in applicable:
        for conflict in conflicts_for(relation, believed, conclusions=conclusions):
            if conflict.state != "possible":
                continue
            succession = infer_succession(
                believed, relation, conclusion_id=str(uuid.uuid4()), now=now
            )
            if succession is None:
                continue
            await repository.record_conclusion(succession.conclusion)
            inferred.append(succession.conclusion)
            conclusions = [*conclusions, succession.conclusion]
        # Recomputed after inference, so a caller is told the state a person
        # would see rather than the one that held for the instant before the
        # explanation was recorded.
        conflicts.extend(conflicts_for(relation, believed, conclusions=conclusions))

    return conflicts, inferred
