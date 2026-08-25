"""HTTP surface for looking at the memory graph.

Read-only, deliberately and for now. Nothing here retracts a claim, accepts a
conclusion or merges two nodes, because a destructive route should not exist
before there is a way to see what it would destroy — and seeing is the harder
half. The write routes are the next piece and they belong beside these.

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

from datetime import datetime
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from bacteria.app.auth.dependencies import CurrentPrincipal
from bacteria.app.core.dependencies import DbSession
from bacteria.app.graph.catalogue import functional
from bacteria.app.graph.constraints import conflicts_for
from bacteria.app.graph.repository import SqlGraphRepository
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
    believed = await repository.current(principal.id)
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
    return [
        ConclusionOut(
            conclusion_id=c.conclusion_id,
            statement=c.statement,
            confidence=c.confidence,
            derived_by=c.derived_by,
            status=c.status,
            recorded_at=c.recorded_at,
            evidence=list(c.evidence),
        )
        for c in conclusions
    ]


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
