"""HTTP surface for looking at the memory graph.

Reading and correcting. The read routes came first deliberately — a destructive
route should not exist before there is a way to see what it would destroy, and
seeing was the harder half — and the write routes are here now because the
alternative is a person watching their own graph hold two mothers for them with
no way to say so.

**Every write is the owner's own, so none of them stage.** A person retracting
their claim is the approver rather than the applicant, and the design's rule is
that the owner's writes are never blocked. What stages is a proposal somebody
else made, and nothing here makes one.

**Ownership is structural rather than checked.** ``chat/`` establishes who and
then, in a second step, whether that caller may have a particular session,
because a session id is a thing a caller names. Nothing here takes an id of
anything: every route asks for *the caller's own graph*, the principal is the
first term of every query, and there is no parameter that could name someone
else's. That makes the ownership rule ``chat/access.py`` warns features about
forgetting a property of the shape here rather than a check to remember.

The distinction matters in the same way that record notes: a broken check
refuses a legitimate caller, a broken filter hands over everyone else's data.
These are filters, so `test_graph_routes.py` asserts the refusal rather than
trusting the shape.

Not built:
    Pagination. A graph grows monotonically and these routes return all of it.
    Fine at the size a personal graph reaches in months, wrong at the size it
    reaches in years, and the fix is the anchor-then-traverse narrowing ADR 0006
    describes for retrieval — which is not built either, so bounding here first
    would bound the wrong end.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from bacteria.app.auth.dependencies import CurrentPrincipal
from bacteria.app.core.dependencies import DbSession
from bacteria.app.graph.catalogue import functional, is_canonical
from bacteria.app.graph.conclusions import Conclusion
from bacteria.app.graph.constraints import conflicts_for
from bacteria.app.graph.log import Assertion
from bacteria.app.graph.repository import (
    SqlGraphRepository,
    UnknownAssertionError,
    UnknownConclusionError,
    UnknownNodeError,
)
from bacteria.app.graph.service import (
    LabelTakenError,
    MismatchedKindsError,
    Outcome,
    confirm,
    link,
    reject,
    rename,
    retract,
)
from bacteria.app.graph.temporal import OPEN_ENDED

router = APIRouter(prefix="/graph", tags=["graph"])


class NodeOut(BaseModel):
    """One thing the graph knows about."""

    node_id: str
    label: str
    kind: str
    first_seen: datetime
    last_seen: datetime


class AssertionOut(BaseModel):
    """One claim, with its two time axes flattened for a reader.

    ``ends`` is a rendered string rather than the raw bound, because the three
    states a bound can be in — a date, open, unknown — are the distinction the
    whole temporal layer rests on, and a JSON ``null`` on the wire cannot carry
    it. A client receiving ``null`` would have to know that the open sentinel is
    a particular timestamp in the year 9999 to tell "still true" from "nobody
    knows", which is exactly the knowledge an API should not require.
    """

    assertion_id: str
    src: str
    dst: str
    rel: str
    ends: str
    starts: Optional[datetime]
    trust: str
    origin: str
    """Whether anybody meant this, which is the only thing that decides if it can
    be spoken. Carried because the console offers *confirm* on a proposal and not
    on a claim already confirmed, and could not tell them apart without it."""

    canonical: bool
    """Whether ``rel`` is a relation the catalogue has agreed to.

    Derived here rather than stored, which is ADR 0007's decision and not an
    optimization: promoting a relation is then an edit to one literal, and every
    past claim reclassifies without a row being touched. Sent because the tail
    being *visible* is the point of recording it — a person cannot learn that
    ``interlocutor`` is junk from a graph that renders it like everything else.
    """

    recorded_at: datetime
    reason: Optional[str]


class ConflictOut(BaseModel):
    """Two claims a rule says cannot both hold, and how sure we are.

    ``state`` is one of conflict, possible or explained. A client should render
    all three differently: the first is a contradiction, the second is missing
    dates, and the third is an assumption someone can disagree with.

    ``sentence`` travels with it because a constraint here is a hypothesis about
    the user's world rather than a rule the system is entitled to enforce — a
    person cannot contest what they cannot read.
    """

    rule: str
    sentence: str
    left: str
    right: str
    state: str


class GraphOut(BaseModel):
    """Everything currently believed, and what disagrees with what."""

    nodes: list[NodeOut]
    assertions: list[AssertionOut]
    conflicts: list[ConflictOut]


class ConclusionOut(BaseModel):
    """A belief the system drew, and the claims it rests on.

    ``evidence`` is always populated. A conclusion whose grounds a person cannot
    follow is one they can only take on faith, which is the opposite of the point
    — and the mandatory link is what makes it possible to say *why* something
    went stale rather than only that it did.
    """

    conclusion_id: str
    statement: str
    confidence: float
    derived_by: str
    status: str
    recorded_at: datetime
    evidence: list[str]


@router.get("", response_model=GraphOut)
async def read_graph(principal: CurrentPrincipal, db: DbSession) -> GraphOut:
    """The caller's own graph as it currently stands.

    "Currently" means believed now — ``recorded_until IS NULL`` — not everything
    ever claimed. The log keeps superseded claims so a past belief stays
    recoverable; a reader looking at their memory wants what it holds, and the
    history is a different question with a different route when someone needs it.

    Conflicts are computed on read rather than stored. They are a function of
    what is believed and which rules exist, so a stored copy would be a cache
    that goes stale the moment either changes — and the thing it would be
    caching is a comparison over a set small enough to walk.
    """
    repository = SqlGraphRepository(db)
    believed = _one_row_per_claim(await repository.current(principal.id))
    conclusions = await repository.depending_on(principal.id, [a.assertion_id for a in believed])

    conflicts = [
        ConflictOut(
            rule=conflict.rule,
            sentence=relation.invariant or relation.sentence,
            left=conflict.left,
            right=conflict.right,
            state=conflict.state,
        )
        for relation in functional()
        for conflict in conflicts_for(relation, believed, conclusions=conclusions)
    ]

    return GraphOut(
        nodes=[
            NodeOut(
                node_id=node.node_id,
                label=node.label,
                kind=node.kind,
                first_seen=node.first_seen,
                last_seen=node.last_seen,
            )
            for node in await repository.nodes(principal.id)
        ],
        assertions=[
            AssertionOut(
                assertion_id=a.assertion_id,
                src=a.src,
                dst=a.dst,
                rel=a.rel,
                ends=_render_end(a.valid.end),
                starts=a.valid.start,
                trust=a.trust,
                origin=a.origin,
                canonical=is_canonical(a.rel),
                recorded_at=a.recorded_at,
                reason=(a.attrs or {}).get("reason"),
            )
            for a in believed
        ],
        conflicts=conflicts,
    )


@router.get("/conclusions", response_model=list[ConclusionOut])
async def read_conclusions(principal: CurrentPrincipal, db: DbSession) -> list[ConclusionOut]:
    """Beliefs the system drew, including the ones that have gone stale.

    Stale ones are returned rather than filtered, because "this rested on
    something that has since changed" is the most useful thing this layer can
    tell a person, and hiding it would leave them looking at a shorter list with
    no indication anything had been withdrawn.
    """
    repository = SqlGraphRepository(db)
    believed = await repository.current(principal.id)
    conclusions = await repository.depending_on(principal.id, [a.assertion_id for a in believed])
    return [_conclusion_out(c) for c in conclusions]


def _conclusion_out(conclusion: Conclusion) -> ConclusionOut:
    """One conclusion as the wire sees it, for both the listing and a write."""
    return ConclusionOut(
        conclusion_id=conclusion.conclusion_id,
        statement=conclusion.statement,
        confidence=conclusion.confidence,
        derived_by=conclusion.derived_by,
        status=conclusion.status,
        recorded_at=conclusion.recorded_at,
        evidence=list(conclusion.evidence),
    )


def _one_row_per_claim(believed: list[Assertion]) -> list[Assertion]:
    """One line per belief, where the log keeps one row per *event*.

    Confirming appends: the proposal stays and the endorsement is a second row
    with the same triple and a different ``origin``. That is right for a log —
    two things happened — and wrong for a page, where it read as the claim
    having been duplicated by the act of agreeing with it.

    **The endorsement wins**, so the id every affordance targets is the confirmed
    one and ``origin`` renders as *confirmed* rather than as a proposal that also
    happens to be confirmed somewhere off screen.

    Conflicts are computed after this, and must be: two rows for one claim would
    otherwise be compared against each other, and a functional relation would
    report a person as contradicting themselves by agreeing.
    """
    kept: dict[tuple[str, str, str, object, object], Assertion] = {}
    for claim in believed:
        key = (claim.src, claim.rel, claim.dst, claim.valid.start, claim.valid.end)
        held = kept.get(key)
        if held is None or (held.origin != "stated" and claim.origin == "stated"):
            kept[key] = claim
    return list(kept.values())


def _render_end(end: Optional[datetime]) -> str:
    """Turn a valid-time end into something a client can branch on.

    Three states, three strings. ``"open"`` says the claim is asserted to still
    hold; ``"unknown"`` says nobody recorded when it stopped; anything else is an
    ISO date. Collapsing the first two — which a nullable timestamp on the wire
    would do — loses the distinction that makes two current claims a
    contradiction rather than an undecidable pair.
    """
    if end is None:
        return "unknown"
    if end == OPEN_ENDED:
        return "open"
    return end.isoformat()


class OutcomeOut(BaseModel):
    """What a write changed, and what it left for a person to look at.

    The same shape for all four verbs, because a caller's next move is the same
    whichever it was: redraw, and show what now needs attention. Carrying the
    engine's `Outcome` through rather than returning 204 is what lets the console
    update without re-fetching the graph to discover it should.
    """

    conflicts: list[ConflictOut]
    inferred: list[ConclusionOut]
    stale: list[ConclusionOut]


class LinkIn(BaseModel):
    """Two nodes the owner says are one thing."""

    left: str
    right: str


class RenameIn(BaseModel):
    """What a node should be called instead."""

    label: str


@router.post("/assertions/{assertion_id}/retract", response_model=OutcomeOut)
async def retract_assertion(
    assertion_id: str, principal: CurrentPrincipal, db: DbSession
) -> OutcomeOut:
    """Stop believing a claim.

    A `POST` to a verb rather than a `DELETE` of the resource, because nothing is
    deleted: the row stays, its belief interval closes, and `state_at` still
    reconstructs what was believed before. `DELETE` would name the wrong act, and
    a route's shape is the first thing anyone reads about what it does.
    """
    repository = SqlGraphRepository(db)
    try:
        claim = await repository.assertion(principal.id, assertion_id)
    except UnknownAssertionError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such assertion") from None

    outcome = await retract(repository, claim, now=datetime.now(timezone.utc))
    await db.commit()
    return _rendered(outcome)


@router.post("/assertions/{assertion_id}/confirm", response_model=OutcomeOut)
async def confirm_assertion(
    assertion_id: str, principal: CurrentPrincipal, db: DbSession
) -> OutcomeOut:
    """Endorse a claim the extractor proposed, so a prompt may be told it.

    The only act on this graph that *keeps* something. Everything else takes
    away, which is why its absence was invisible: the graph worked, quietly,
    without ever mattering.

    Appends rather than editing. The proposal stays and the two rows differ in
    ``origin``, so the log records the endorsement as its own event — and
    confirming twice writes nothing, because saying yes twice is one yes.
    """
    repository = SqlGraphRepository(db)
    try:
        claim = await repository.assertion(principal.id, assertion_id)
    except UnknownAssertionError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such assertion") from None

    outcome = await confirm(
        repository,
        claim,
        assertion_id=str(uuid.uuid4()),
        now=datetime.now(timezone.utc),
    )
    await db.commit()
    return _rendered(outcome)


@router.post("/conclusions/{conclusion_id}/reject", response_model=OutcomeOut)
async def reject_conclusion(
    conclusion_id: str, principal: CurrentPrincipal, db: DbSession
) -> OutcomeOut:
    """Withdraw an inferred belief the owner disagrees with.

    The conflict it was explaining returns to *possible*, which is the honest
    state it held before anyone assumed anything — and it will not be explained
    the same way again.
    """
    repository = SqlGraphRepository(db)
    try:
        outcome = await reject(
            repository, principal.id, conclusion_id, now=datetime.now(timezone.utc)
        )
    except UnknownConclusionError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such conclusion") from None

    await db.commit()
    return _rendered(outcome)


@router.post("/nodes/{node_id}/rename", response_model=NodeOut)
async def rename_node(
    node_id: str, body: RenameIn, principal: CurrentPrincipal, db: DbSession
) -> NodeOut:
    """Correct what a node is called.

    409 when the name is taken, and the message is the point: two nodes that
    should share a name are two nodes to link, so the refusal is an invitation
    rather than a wall.
    """
    repository = SqlGraphRepository(db)
    try:
        node = await rename(
            repository, principal.id, node_id, body.label, now=datetime.now(timezone.utc)
        )
    except UnknownNodeError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such node") from None
    except LabelTakenError as taken:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"{taken.label!r} already names another node; link them instead",
        ) from None

    await db.commit()
    return NodeOut(
        node_id=node.node_id,
        label=node.label,
        kind=node.kind,
        first_seen=node.first_seen,
        last_seen=node.last_seen,
    )


@router.post("/links", response_model=OutcomeOut, status_code=201)
async def link_nodes(body: LinkIn, principal: CurrentPrincipal, db: DbSession) -> OutcomeOut:
    """Say two nodes are the same thing.

    201, because this creates an assertion — the link is a claim like any other
    and can be retracted through the route above, which is the whole argument for
    linking rather than merging.
    """
    repository = SqlGraphRepository(db)
    try:
        outcome = await link(
            repository,
            principal.id,
            body.left,
            body.right,
            assertion_id=str(uuid.uuid4()),
            now=datetime.now(timezone.utc),
        )
    except UnknownNodeError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such node") from None
    except MismatchedKindsError as mismatch:
        raise HTTPException(status.HTTP_409_CONFLICT, str(mismatch)) from None

    await db.commit()
    return _rendered(outcome)


def _rendered(outcome: Outcome) -> OutcomeOut:
    """One `Outcome` as the wire sees it.

    Conflicts lose their rule sentence here and keep their state, because a
    caller that just wrote is redrawing rather than reading: `GET /graph` carries
    the sentences, and repeating them on every write would make the two surfaces
    two places to keep one wording.
    """
    return OutcomeOut(
        conflicts=[
            ConflictOut(
                rule=c.rule,
                sentence="",
                left=c.left,
                right=c.right,
                state=c.state,
            )
            for c in outcome.conflicts
        ],
        inferred=[_conclusion_out(c) for c in outcome.inferred],
        stale=[_conclusion_out(c) for c in outcome.stale],
    )
