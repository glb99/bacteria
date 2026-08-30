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

from bacteria.app.graph.catalogue import Relation, read_as
from bacteria.app.graph.conclusions import Conclusion, stale_after
from bacteria.app.graph.constraints import Conflict, conflicts_for
from bacteria.app.graph.identity import SELF, Node, normalize, owner_node_id
from bacteria.app.graph.inference import infer_succession
from bacteria.app.graph.log import Assertion, log_expire
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
    relations: Optional[Sequence[Relation]] = None,
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
        # After the write, so the closing sees the batch it belongs to. A claim
        # that ends a role is usually stated in the same breath as the one that
        # replaces it, and closing before the write would leave the old belief
        # standing until the next turn.
        await _close_superseded(repository, fresh, believed, now)

    conflicts, inferred = await _reconcile(
        repository, owner, {a.rel for a in assertions}, relations, now
    )
    return Outcome(recorded=len(fresh), conflicts=conflicts, inferred=inferred)


async def _close_superseded(
    repository: SqlGraphRepository,
    fresh: Sequence[Assertion],
    believed: Sequence[Assertion],
    now: datetime,
) -> None:
    """Stop believing an open claim that a dated one about the *same triple* replaces.

    **The narrowest possible revision, and narrow is the whole point.** "Diane is
    Acme's CTO" and "Diane left Acme in February" are not two beliefs about the
    world: the second is the first plus a fact about when it stopped. Same
    ``(user_id, src, rel, dst)``, one open end and one known end — the dated
    claim is strictly more informed and nothing else could be true.

    So this needs no judgement about *which* claim a correction refers to, which
    is the thing an extractor cannot be trusted with. The triple is identical, so
    there is nothing to resolve and nothing to conflate.

    **A model must not be able to unbelieve things**, and this is the line that
    keeps that true. A wrongly *added* claim is visible: it shows as a conflict
    and a person can retract it. A wrongly *closed* one is invisible — it simply
    stops appearing — so revision is the unrecoverable direction and only the
    arithmetic case is allowed through it. "Actually it was Bob, not Diane" has a
    different ``dst``, stays a conflict, and remains a person's decision.

    Left standing, the old claim did two kinds of harm at once, both seen in one
    real conversation: it contradicted the successor, and it blocked the
    succession inference by being a second open undated claim.
    """
    for claim in fresh:
        if not _has_known_end(claim):
            continue
        for standing in believed:
            if _claim_of(standing)[:4] != _claim_of(claim)[:4]:
                continue
            if standing.valid.end != OPEN_ENDED:
                continue
            await repository.close(replace(standing, recorded_until=now, closed_by="superseded"))


def _has_known_end(assertion: Assertion) -> bool:
    """An end that is a real date — neither unknown nor the open sentinel."""
    end = assertion.valid.end
    return end is not None and end != OPEN_ENDED


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
            a = replace(a, valid=Interval(None, a.valid.end), attrs=_withdrawn(a.attrs))
        stripped.append(a)
    return stripped


def _withdrawn(attrs: Optional[dict]) -> Optional[dict]:
    """Record that a start the model gave was taken back, rather than accepted.

    ``since_said`` is written by extraction, before this runs, and means *the
    transcript supported this*. When the start is stripped here that stops being
    true, and a row whose ``valid_from`` is null while its ``attrs`` still claim
    the date was said is a log that misreports its own decision — which is worse
    than a missing note, because it would be believed.
    """
    if not attrs or "since_said" not in attrs:
        return attrs
    amended = dict(attrs)
    amended["since_withdrawn"] = amended.pop("since_said")
    return amended


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
    relations: Optional[Sequence[Relation]] = None,
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
    wanted = {r.name for r in (relations or repository.vocabulary.preferences())}
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


@dataclass(frozen=True)
class Claim:
    """One confirmed fact, as a sentence and the words behind it.

    ``statement`` is rendered from the catalogue rather than assembled here, so a
    fact reads the way the vocabulary says it reads — the same renderer ADR 0009
    uses for a conclusion, for the same reason: this text is for a person, or for
    a model, and node ids are for neither.

    ``assertion_id`` is the key a supplier will hand back. Unique, stable, and
    never displayed, so nothing has to invent one — which is the trap widening
    the keyed projection would have walked into.
    """

    assertion_id: str
    statement: str
    reason: str
    subject: str
    object: str


async def claims_for(
    repository: SqlGraphRepository,
    user_id: str,
    *,
    anchors: Sequence[str] = (),
    as_of: Optional[datetime] = None,
) -> list[Claim]:
    """The facts this person has confirmed, optionally narrowed to some nodes.

    **The second function that decides what may be spoken, and there must never
    be a third.** ADR 0010 §5 wanted one; ADR 0011 accepts two because the keyed
    projection and a per-turn candidate list are different shapes, and one
    function serving both would need a flag — which is how *speakable* and *not
    speakable* come to depend on reading a call site correctly.

    So the rule is stated rather than left to a reader: ``origin == "stated"``,
    here and in :func:`preferences_for`, and nowhere else.

    ``anchors`` narrows to claims touching those nodes at either end. Empty means
    everything confirmed, which is what a caller comparing against recency wants
    — narrowing is the supplier's job and this is the read it narrows.

    ``as_of`` reads the graph as it was *believed* at a past moment rather than
    now, and it is deliberately a parameter here rather than a third function.
    The rule above is that exactly two functions decide what may be spoken; a
    third would make *speakable* depend on reading a call site correctly. This
    one changes **when**, never **whether** — ``origin == "stated"`` still gates
    every row, and a claim confirmed after ``as_of`` is absent because it was not
    yet believed, not because the rule moved.

    That distinction is what makes grading a past run honest. §3 of the model
    gives recorded time exactly one job — reconstructing the memory a run
    actually saw — and reading ``current()`` instead would score yesterday's turn
    against today's beliefs, which flatters every strategy equally and settles
    nothing.
    """
    labels = {node.node_id: node.label for node in await repository.nodes(user_id)}
    wanted = set(anchors)

    found: list[Claim] = []
    believed = (
        await repository.current(user_id)
        if as_of is None
        else await repository.believed_at(user_id, as_of)
    )
    for assertion in believed:
        if assertion.origin != "stated":
            continue
        relation = repository.vocabulary.lookup(assertion.rel)
        if relation is None:
            # Tail relations are excluded, and not to be tidy: the sentence a
            # claim renders with comes from the catalogue, so a relation without
            # one cannot be written down for a model without inventing phrasing
            # nobody approved.
            continue
        if wanted and assertion.src not in wanted and assertion.dst not in wanted:
            continue
        attrs = assertion.attrs or {}
        found.append(
            Claim(
                assertion_id=assertion.assertion_id,
                statement=read_as(
                    relation,
                    labels.get(assertion.src, assertion.src),
                    labels.get(assertion.dst, assertion.dst),
                ),
                reason=str(attrs.get("reason") or "confirmed by the owner"),
                subject=assertion.src,
                object=assertion.dst,
            )
        )
    return sorted(found, key=lambda c: c.statement)


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
    wanted = {r.name for r in (relations or repository.vocabulary.preferences())}
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


async def confirm(
    repository: SqlGraphRepository,
    assertion: Assertion,
    *,
    assertion_id: str,
    now: datetime,
    relations: Optional[Sequence[Relation]] = None,
) -> Outcome:
    """Endorse a claim the extractor proposed, making it speakable.

    **The half of curation nobody built.** Every other act on this graph takes
    something away — retract, reject, rename onto a name that displaces another.
    This is the one that keeps something, and it is what a supplier needs: a
    supplier may return only what a person confirmed, so until now anchor
    resolution would have traversed correctly and found nothing it was allowed to
    hand over.

    **Appends rather than flipping a flag.** The proposal stays exactly where it
    was and the two rows differ in ``origin``, because ratification is not a
    property of a claim — it is the owner making the claim, and the log records
    events. ``_unrepeated`` keys on ``origin`` precisely so this is not swallowed
    as a restatement of what the model already said.

    A second confirmation of the same claim writes nothing and reports nothing
    written, which is what the repeat rule is for: saying yes twice is one yes.

    ``now`` must be later than the claim's own ``recorded_at``, and in practice
    always is — a person confirms something they have read. Passing the same
    instant collides on ``uq_assertion_claim_recorded``, which is the constraint
    doing its job: at one moment there is one belief about a claim, and a
    confirmation *is* a second belief about it.

    **Confirming a name also relabels its subject**, which is ADR 0012 §5 and the
    only place an act on the log reaches the node table. The split it keeps is
    ADR 0009's: the claim is what is *true* and carries provenance and history;
    the label is what is *drawn* and carries neither. So the label follows the
    claim rather than standing in for it — the arrangement 0012 rejected was the
    reverse, a label with no ``origin`` being read as though it were a fact.

    Only on confirmation, never on the proposal. An extracted name is a guess
    until somebody says otherwise, and a graph that relabelled its owner the
    first time a model heard a word would be drawing that guess as settled.
    """
    stated = replace(
        assertion,
        assertion_id=assertion_id,
        origin="stated",
        # The owner is the one confirming, whatever channel the claim arrived
        # through. `trust` records the channel and would be a lie here if it kept
        # saying `third-party` about a sentence a person just endorsed.
        trust="user",
        recorded_at=now,
        recorded_until=None,
        closed_by=None,
    )
    outcome = await observe(repository, [stated], now=now, relations=relations)

    if stated.rel == repository.vocabulary.names:
        await _relabel_from_name(repository, stated, now=now)
    return outcome


async def _relabel_from_name(
    repository: SqlGraphRepository, claim: Assertion, *, now: datetime
) -> None:
    """Draw the subject of a confirmed name-claim under the name it states.

    Best-effort, and deliberately so: a name already taken by another node of the
    same kind raises :class:`LabelTakenError`, and that must not undo a
    confirmation the owner just made. The claim is the record; failing to redraw
    it leaves the graph looking stale rather than wrong, which is the recoverable
    direction — and the person can rename by hand from the console.
    """
    label = (await _node(repository, claim.user_id, claim.dst)).label
    try:
        await rename(repository, claim.user_id, claim.src, label, now=now)
    except LabelTakenError:
        return


async def retract(
    repository: SqlGraphRepository,
    assertion: Assertion,
    *,
    now: datetime,
    relations: Optional[Sequence[Relation]] = None,
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
    # Every row saying this, not only the one named. A confirmed claim is two
    # rows -- the proposal and the endorsement -- and closing one would leave the
    # other believed, so the claim would still be there and the retraction would
    # look like it had failed. One belief, recorded twice, stops being believed
    # once.
    # Compared without `origin`, which the repeat key includes and this must not:
    # there it separates a guess from an endorsement, and here those are the two
    # rows that have to go together.
    target = _claim_of(assertion)[:5]
    same = [a for a in await repository.current(owner) if _claim_of(a)[:5] == target]
    ids = [a.assertion_id for a in same] or [assertion.assertion_id]
    dependents = await repository.depending_on(owner, ids)

    for doomed in same or [assertion]:
        await repository.close(log_retract(doomed, at=now))

    now_stale = stale_after(dependents, ids)
    for conclusion in now_stale:
        await repository.set_status(owner, conclusion.conclusion_id, "stale")

    conflicts, inferred = await _reconcile(repository, owner, {assertion.rel}, relations, now)
    return Outcome(conflicts=conflicts, inferred=inferred, stale=now_stale)


async def expire_tail(
    repository: SqlGraphRepository,
    user_id: str,
    *,
    before: datetime,
    now: datetime,
    dry_run: bool = False,
) -> list[Assertion]:
    """Close tail claims nobody came back to, and say which.

    **The only thing here that removes without being asked**, and it is narrow on
    purpose. A claim qualifies on three counts at once:

    - **Its relation is not in the catalogue.** A canonical claim uses agreed
      vocabulary and stays however long it goes unread.
    - **Nobody confirmed it.** ``origin`` is still ``inferred``, so no person ever
      meant it. A confirmed tail claim is somebody's deliberate act and outlives
      any clock.
    - **It is older than ``before``.**

    **Why the tail and not everything.** ADR 0007 keeps an unratified relation
    *because it is evidence for what the catalogue should become* — and evidence
    has a shelf life. A word still unratified and unconfirmed after the window has
    been available the whole time and nothing came of it, which is an answer
    rather than an absence.

    It also repairs the promotion tally, which was not the reason for choosing it.
    ``tally_relations`` counts every tail claim ever written, so a word seen once
    a year climbs toward three forever; expiry makes three occurrences mean three
    *recent* ones, which is the live regularity the rule of three was meant to
    detect rather than a lifetime total.

    Closes rather than deletes, so this is retention in the sense §2 principle 8
    permits: belief ends, the row stays, and ``closed_by`` says a clock did it
    rather than a person.

    ``dry_run`` returns what would be closed and writes nothing, so the chore's
    preview and its action cannot disagree.

    Not built:
        Iterating owners. This takes one, because the repository is owner-scoped
        and a chore that quietly writes across everybody is a different thing
        wanting a different review. The caller loops when there is more than one
        owner to loop over.
    """
    believed = await repository.current(user_id)
    # A confirmation appends a row rather than flipping a flag, so a claim
    # somebody meant is *two* rows and only one of them says `stated`. Checking
    # `origin` alone takes the proposal out from under the endorsement -- found by
    # running the sweep over a real graph, where its one candidate was a claim the
    # owner had confirmed the day before. Compared on the triple and its interval,
    # which is `_claim_of` minus `origin`, for the reason `retract` drops it too:
    # there those are the two rows that belong together, and so are these.
    endorsed = {_claim_of(a)[:5] for a in believed if a.origin == "stated"}
    doomed = [
        claim
        for claim in believed
        if not repository.vocabulary.is_canonical(claim.rel)
        and claim.origin == "inferred"
        and claim.recorded_at < before
        and _claim_of(claim)[:5] not in endorsed
    ]
    if not doomed:
        return []

    if dry_run:
        # One selection, two callers. The chore reports before it writes, and a
        # report built from a second copy of this filter is a report that drifts
        # from what the sweep would do -- which is the one thing an operator is
        # relying on it not to.
        return doomed

    ids = [claim.assertion_id for claim in doomed]
    dependents = await repository.depending_on(user_id, ids)
    for claim in doomed:
        await repository.close(log_expire(claim, at=now))

    # The same walk retraction does, for the same reason: a conclusion resting on
    # a claim that has gone is not wrong, it is unexamined.
    for conclusion in stale_after(dependents, ids):
        await repository.set_status(user_id, conclusion.conclusion_id, "stale")
    return doomed


async def reject(
    repository: SqlGraphRepository,
    owner: str,
    conclusion_id: str,
    *,
    now: datetime,
    relations: Optional[Sequence[Relation]] = None,
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
    relations: Optional[Sequence[Relation]],
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
    # The single place a missing vocabulary is resolved, and the reason every
    # caller above may leave `relations` as `None`. It falls back to the words
    # the repository was opened with rather than to a module-level literal: the
    # rules that fire on an architecture claim must be architecture's, and until
    # the vocabulary rode here there was only one set the substrate could reach.
    vocabulary = relations if relations is not None else repository.vocabulary.relations

    believed = await repository.current(owner)
    conclusions = await repository.depending_on(owner, [a.assertion_id for a in believed])
    applicable = [r for r in vocabulary if r.name in affected]

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
