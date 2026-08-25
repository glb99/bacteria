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
from datetime import datetime, timezone
from typing import Optional, Sequence

from bacteria.app.graph.catalogue import CATALOGUE, Relation
from bacteria.app.graph.catalogue import preferences as preference_relations
from bacteria.app.graph.conclusions import Conclusion, stale_after
from bacteria.app.graph.constraints import Conflict, conflicts_for
from bacteria.app.graph.identity import SELF, Node, normalize, owner_node_id
from bacteria.app.graph.inference import infer_succession
from bacteria.app.graph.log import Assertion
from bacteria.app.graph.log import retract as log_retract
from bacteria.app.graph.repository import SqlGraphRepository, UnknownNodeError
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


def _claim_of(assertion: Assertion) -> tuple[str, str, str, str, Interval, str]:
    """What makes two assertions the same claim, for the purpose above.

    ``origin`` is in the key and ``trust`` is deliberately not, and the pair reads
    as inconsistent until you ask what each says. A claim arriving through a
    different channel is news about the channel; the **owner confirming what the
    model guessed is news about the world**, and it is how a proposal becomes
    something a projection may speak. Swallowing that as a restatement would make
    ratification impossible to record.
    """
    return (
        assertion.user_id,
        assertion.src,
        assertion.rel,
        assertion.dst,
        assertion.valid,
        assertion.origin,
    )


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


class LabelTakenError(ValueError):
    """A rename would give two nodes of one kind the same name.

    Refused rather than allowed, and the reason is ADR 0006's asymmetry rather
    than tidiness. ``node_named`` matches on ``(kind, normalized label)``, so two
    matching nodes make every later mention resolve to whichever the database
    returns first — an arbitrary answer to "which Diane", drifting toward
    collapsing two people into one, which is the direction that cannot be undone.

    The refusal is the negotiation, not a dead end: two nodes that *should* share
    a name are two nodes to link, and :func:`link` is the way to say so.
    """

    def __init__(self, label: str, node_id: str) -> None:
        super().__init__(f"{label!r} already names node {node_id}")
        self.label = label
        self.node_id = node_id


async def rename(
    repository: SqlGraphRepository, user_id: str, node_id: str, label: str, *, now: datetime
) -> Node:
    """Correct what a node is called.

    The missing half of the reserved owner node, whose id is derived from the
    user id *precisely so* that its label stays correctable — and which nothing
    corrected until now, leaving every graph owned by someone called "self".

    **A label is a display name, not a record.** What a person is called is a
    fact and belongs in the log; this is what to draw. So there is no history
    here and none is lost, which is why this is an update in a package that
    otherwise never overwrites anything.

    Raises :class:`LabelTakenError` when another node of the same kind already
    carries the name.
    """
    existing = await repository.node_named(
        user_id, (await _node(repository, user_id, node_id)).kind, label
    )
    if existing is not None and existing.node_id != node_id:
        raise LabelTakenError(label, existing.node_id)
    return await repository.relabel_node(user_id, node_id, label)


async def link(
    repository: SqlGraphRepository,
    user_id: str,
    left: str,
    right: str,
    *,
    assertion_id: str,
    now: datetime,
) -> Outcome:
    """Say that two nodes are the same thing, without merging them.

    ADR 0006's identity rule, finally given a writer: nodes are **linked, never
    merged**. Both keep their ids, their labels and every assertion recorded
    against them, and the claim that they are one thing is an assertion like any
    other — provenanced, contestable, retractable, and usable as evidence.

    That is what makes minting a node per distinct name safe. Splitting one
    person across two nodes is recoverable *because this exists*; it was the
    missing half of an argument the design had been making since the beginning.

    **Refuses two kinds.** A person is not an organization, and a claim that they
    are the same thing is a mistake rather than a merge — the kinds are the one
    check available here, since nothing else can tell a bold identification from
    a slip.

    Nothing in the read surface reads the link yet, so the first use of this
    changes nothing visible. That is correct and will look like a bug.
    """
    one, other = await _node(repository, user_id, left), await _node(repository, user_id, right)
    if one.kind != other.kind:
        raise MismatchedKindsError(one.kind, other.kind)

    claim = Assertion(
        assertion_id=assertion_id,
        user_id=user_id,
        src=one.node_id,
        dst=other.node_id,
        rel="same_as",
        # Open-ended: two things that are the same thing did not become so, and
        # an unknown start would make the claim undecidable against every other
        # claim about either of them.
        valid=Interval(None, OPEN_ENDED),
        recorded_at=now,
        trust="user",
    )
    return await observe(repository, [claim], now=now)


class MismatchedKindsError(ValueError):
    """A link between two different kinds of thing."""

    def __init__(self, one: str, other: str) -> None:
        super().__init__(f"cannot link a {one} to a {other}")


async def _node(repository: SqlGraphRepository, user_id: str, node_id: str) -> Node:
    found = await repository.node(user_id, node_id)
    if found is None:
        raise UnknownNodeError(node_id)
    return found


@dataclass(frozen=True)
class Preference:
    """One keyed fact drawn out of the graph.

    Carries what a keyed memory needs rather than only the pair, because the
    caller that turns these into ``MemoryEntry`` values would otherwise have to
    go back to the log for the words behind each one — and a second read is a
    second chance for the two to disagree.

    ``reason`` comes from the claim's ``attrs``, which is where the extractor put
    the transcript's own wording. A preference with no recorded reason cannot be
    reviewed later, which is why the agent's ``MemoryEntry`` requires one.
    """

    key: str
    value: str
    reason: str
    source: str
    scope: str
    recorded_at: datetime


async def preferences_for(
    repository: SqlGraphRepository,
    user_id: str,
    *,
    session_id: Optional[str] = None,
    relations: Sequence[Relation] = (),
) -> list[Preference]:
    """The graph as keyed memory: one answer per key, or none.

    **The projection, and it is mechanical.** For each preference relation, the
    believed claim the owner stated, rendered as key and value. No ranking, no
    model call, no choice — the relation *is* the key, because "one slot per key"
    and "one ``dst`` per ``(src, rel)`` at a time" are the same statement and the
    catalogue already says the second.

    **Only what the owner stated.** An extracted preference is ``inferred`` and
    does not appear here however confident it looks, which is what keeps the
    agent's rule — *memory is written by the owner, not the model* — true of a
    system where the model does nearly all of the writing. The model may propose;
    it cannot make its proposal speakable.

    **Session scope narrows, it does not widen.** A claim scoped to a session
    appears only when that session is the one asking; a user-scoped claim always
    does.

    Two believed answers for one key is a contradiction the constraint layer has
    already flagged, and this takes the most recently recorded — because a caller
    that asked for the tone needs *an* answer, and returning none for a key under
    dispute is worse than returning the newer of two.
    """
    wanted = {r.name for r in (relations or preference_relations())}
    if not wanted:
        return []

    owner_node = await owner(repository, user_id, now=datetime.now(timezone.utc))
    labels = {n.node_id: n.label for n in await repository.nodes(user_id)}

    newest: dict[str, Assertion] = {}
    for claim in await repository.current(user_id):
        if claim.rel not in wanted or claim.origin != "stated":
            continue
        if claim.src != owner_node.node_id:
            continue
        if claim.scope == "session" and claim.session_id != session_id:
            continue
        held = newest.get(claim.rel)
        if held is None or claim.recorded_at > held.recorded_at:
            newest[claim.rel] = claim

    return [_preference(rel, claim, labels) for rel, claim in sorted(newest.items())]


def _preference(rel: str, claim: Assertion, labels: dict[str, str]) -> Preference:
    attrs = claim.attrs or {}
    return Preference(
        key=rel,
        value=labels.get(claim.dst, claim.dst),
        reason=str(attrs.get("reason") or "recorded in the graph"),
        source=str(attrs.get("source") or ("owner" if claim.origin == "stated" else "graph")),
        scope=claim.scope,
        recorded_at=claim.recorded_at,
    )


async def proposals_from(
    repository: SqlGraphRepository,
    user_id: str,
    *,
    session_id: Optional[str] = None,
    relations: Sequence[Relation] = (),
) -> list[Preference]:
    """Preferences the graph holds and may **not** speak.

    The mirror of :func:`preferences_for`, and separate from it on purpose. That
    function is the one place deciding what reaches a prompt — ADR 0010 §5 rests
    on it being one place — so widening it with a flag would put "speakable" and
    "not speakable" behind the same argument and make the guarantee depend on
    reading a call site correctly.

    Everything here is ``inferred``: something worked it out, nobody said it.
    """
    wanted = {r.name for r in (relations or preference_relations())}
    if not wanted:
        return []

    owner_node = await owner(repository, user_id, now=datetime.now(timezone.utc))
    labels = {n.node_id: n.label for n in await repository.nodes(user_id)}

    found: list[Preference] = []
    for claim in await repository.current(user_id):
        if claim.rel not in wanted or claim.origin != "inferred":
            continue
        if claim.src != owner_node.node_id:
            continue
        if claim.scope == "session" and claim.session_id != session_id:
            continue
        found.append(_preference(claim.rel, claim, labels))
    return sorted(found, key=lambda p: (p.key, p.value))


async def retract(
    repository: SqlGraphRepository,
    assertion: Assertion,
    *,
    now: datetime,
    relations: Sequence[Relation] = CATALOGUE,
) -> Outcome:
    """Stop believing a claim, without stating anything in its place.

    The counterpart to :func:`revise`, and it shares that function's real work:
    everything resting on the claim has to be marked, because a belief whose
    premise has gone is not thereby wrong — it is unexamined, which is a
    different state and the one worth showing a person.

    ``recorded`` is zero. Nothing was written; a row was closed, and a caller
    counting writes should not be told otherwise.

    **The rules run afterwards**, for the same reason :func:`observe` runs them
    after its write: retracting one of two contradictory claims is precisely how
    a conflict stops existing, and evaluating first would report the state the
    owner was trying to leave.
    """
    owner = assertion.user_id
    dependents = await repository.depending_on(owner, [assertion.assertion_id])

    await repository.close(log_retract(assertion, at=now))

    now_stale = stale_after(dependents, [assertion.assertion_id])
    for conclusion in now_stale:
        await repository.set_status(owner, conclusion.conclusion_id, "stale")

    conflicts, inferred = await _reconcile(repository, owner, {assertion.rel}, relations, now)
    return Outcome(conflicts=conflicts, inferred=inferred, stale=now_stale)


async def reject(
    repository: SqlGraphRepository,
    owner: str,
    conclusion_id: str,
    *,
    now: datetime,
    relations: Sequence[Relation] = CATALOGUE,
) -> Outcome:
    """Withdraw an inferred belief the owner disagrees with.

    A status change, where :func:`retract` closes a row, and the asymmetry is
    worth knowing rather than inheriting: a conclusion is a *derived belief and
    may be recomputed*, so moving its status loses nothing — the log still holds
    everything it was drawn from. An assertion is a *record of what was claimed*,
    so mutating one would lose the claim. Two tables, two policies, and the
    criterion is recomputability rather than importance.

    The conflict the conclusion was explaining returns to ``possible``, which is
    the honest state it was in before anyone assumed anything — and
    :func:`_reconcile` will not now propose the same explanation again. See
    :func:`_already_considered`.
    """
    await repository.set_status(owner, conclusion_id, "retracted")

    believed = await repository.current(owner)
    conflicts, inferred = await _reconcile(
        repository, owner, {a.rel for a in believed}, relations, now
    )
    return Outcome(conflicts=conflicts, inferred=inferred)


def _already_considered(conclusions: Sequence[Conclusion], pair: set[str], derived_by: str) -> bool:
    """Has this exact inference been drawn before, whatever became of it?

    **Status is deliberately not consulted**, and that is the whole point. A
    retracted conclusion makes its conflict ``possible`` again, and ``_reconcile``
    infers on ``possible`` conflicts — so without this, rejecting an explanation
    caused the very next extraction touching that relation to record a fresh
    active copy of it. The owner's "no" was undone by the next thing they said
    about the subject, silently.

    That is the re-proposal failure the model predicts for merge suggestions —
    *a rejection that merely deletes leaves the same similarity proposing the
    same merge forever* — reached from the other direction. A rejection has to be
    remembered, not merely applied.

    Keyed on the evidence pair rather than on the conflict, because a conclusion
    is identified by what it rests on. New evidence is a new inference and should
    be proposed again; the same two premises are the question already answered.
    """
    return any(c.derived_by == derived_by and pair <= set(c.evidence) for c in conclusions)


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

    # Read once, and only when a rule might fire: this is the only thing in the
    # reconciliation that needs a node's *name* rather than its id, and it needs
    # it so that a conclusion's statement is readable by the person expected to
    # disagree with it.
    labels = (
        {node.node_id: node.label for node in await repository.nodes(owner)} if applicable else {}
    )

    conflicts: list[Conflict] = []
    inferred: list[Conclusion] = []
    for relation in applicable:
        for conflict in conflicts_for(relation, believed, conclusions=conclusions):
            if conflict.state != "possible":
                continue
            if _already_considered(
                conclusions, {conflict.left, conflict.right}, "constraint-inference"
            ):
                continue
            succession = infer_succession(
                believed, relation, labels=labels, conclusion_id=str(uuid.uuid4()), now=now
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
