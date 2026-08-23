"""Where the memory graph's rows become the values the engine reasons about.

The boundary, and the only module in this package that knows SQLModel exists.
Everything above it — :mod:`~bacteria.app.graph.temporal`,
:mod:`~bacteria.app.graph.constraints`, :mod:`~bacteria.app.graph.inference` —
works on frozen dataclasses and is tested without a database. That split is the
same one ``chat/repository.py`` makes, and it buys the same thing: no caller can
hold a live handle on a row and write through it by accident.

**Reads are detached.** Every method returns dataclasses built from rows, never
the rows themselves. Handing back a :class:`~bacteria.app.graph.models.GraphAssertion`
would give a caller something that looks like a value and is a pending database
write, and "the assertion log is append-only" would become a convention rather
than a property.

**Every method takes a ``user_id``, and it is in the query rather than checked
after.** One person's graph must never be reachable from another's, and the way
that fails is a filter someone forgot rather than a rule someone broke.
``chat/access.py`` records the cost of relying on per-feature diligence: "an
ownership rule per feature, forgotten silently, with nothing in the build to
notice. Ingestion has not written one." Here the owner is part of the node key
and the first term of every ``WHERE``.

Not built:
    Pagination, and it will matter here sooner than it does for transcripts. A
    graph grows monotonically and :meth:`SqlGraphRepository.believed_at` loads a
    user's whole believed set, which is fine while a graph is thousands of rows
    and is the wrong shape at a million. The narrowing that fixes it is the
    anchor-then-traverse path ADR 0006 describes, which is not built either, so
    adding a limit here first would bound the wrong end.
"""

import uuid
from datetime import datetime, timezone
from typing import Iterable, Optional, Sequence

from sqlalchemy import or_
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from bacteria.app.graph.conclusions import Conclusion
from bacteria.app.graph.identity import Node, normalize
from bacteria.app.graph.log import Assertion
from bacteria.app.graph.models import (
    GraphAssertion,
    GraphConclusion,
    GraphConclusionEvidence,
    GraphNode,
)
from bacteria.app.graph.temporal import Interval


def _as_utc(value: datetime) -> datetime:
    """Reattach UTC to a datetime a backend handed back without one.

    A no-op against Postgres, which returns what ``DateTime(timezone=True)``
    promises. Kept for the reason ``chat/repository.py`` gives for its twin: this
    is the boundary where stored rows become plain values, and an aware datetime
    is part of what that hand-off promises. A naive one compares as local time
    and every comparison in :mod:`~bacteria.app.graph.temporal` is a comparison.
    """
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _optional_utc(value: Optional[datetime]) -> Optional[datetime]:
    """The same, for the bounds where ``None`` is a meaning rather than a gap.

    ``None`` here is *unknown* — for ``recorded_until``, *still believed* — and
    must survive the trip untouched. Defaulting it to anything would replace a
    state the whole temporal layer distinguishes with one it cannot.
    """
    return None if value is None else _as_utc(value)


def _to_assertion(row: GraphAssertion) -> Assertion:
    return Assertion(
        assertion_id=row.assertion_id,
        user_id=row.user_id,
        src=row.src,
        rel=row.rel,
        dst=row.dst,
        valid=Interval(_optional_utc(row.valid_from), _optional_utc(row.valid_to)),
        recorded_at=_as_utc(row.recorded_at),
        recorded_until=_optional_utc(row.recorded_until),
        trust=row.trust,  # ty: ignore[invalid-argument-type]
        attrs=row.attrs or None,
        session_id=row.session_id,
        run_id=row.run_id,
    )


def _to_row(assertion: Assertion) -> GraphAssertion:
    return GraphAssertion(
        assertion_id=assertion.assertion_id,
        user_id=assertion.user_id,
        src=assertion.src,
        rel=assertion.rel,
        dst=assertion.dst,
        attrs=assertion.attrs or {},
        valid_from=assertion.valid.start,
        valid_to=assertion.valid.end,
        recorded_at=assertion.recorded_at,
        recorded_until=assertion.recorded_until,
        trust=assertion.trust,
        session_id=assertion.session_id,
        run_id=assertion.run_id,
    )


def _to_node(row: GraphNode) -> Node:
    return Node(
        user_id=row.user_id,
        node_id=row.node_id,
        label=row.label,
        kind=row.kind,
        first_seen=_as_utc(row.first_seen),
        last_seen=_as_utc(row.last_seen),
    )


def _to_conclusion(row: GraphConclusion, evidence: Sequence[str]) -> Conclusion:
    return Conclusion(
        conclusion_id=row.conclusion_id,
        user_id=row.user_id,
        statement=row.statement,
        evidence=tuple(evidence),
        confidence=row.confidence,
        derived_by=row.derived_by,  # ty: ignore[invalid-argument-type]
        recorded_at=_as_utc(row.recorded_at),
        status=row.status,  # ty: ignore[invalid-argument-type]
    )


class SqlGraphRepository:
    """Reads and writes the assertion log, in the caller's transaction.

    Args:
        session: An open database session. Injected rather than created here, so
            transaction scope belongs to whoever knows what a unit of work is —
            the same arrangement ``SqlSessionRepository`` has, and the reason a
            revision and its supersession can be made atomic by a caller without
            this class knowing what else is in flight.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._db = session

    async def record(self, assertions: Iterable[Assertion]) -> None:
        """Append claims. Nothing here updates anything.

        **Recording the same assertion twice is a no-op, not an error.** Writers
        derive an assertion id from the claim, so an identical id means an
        identical claim — and a retried job that re-reads the same slice must
        land where it did rather than crash. The first version relied on the
        unique constraint for that and did not survive a test of it: an
        identical primary key raises rather than being ignored, so a crash
        between the write and its watermark turned every retry into a failure.

        Conflicts are ignored on the primary key alone. The constraint on
        ``(user_id, src, rel, dst, recorded_at)`` still raises, and should: two
        *different* ids for one claim at one instant means two writers disagreed
        about how ids are derived, which is worth hearing about rather than
        silently resolving.
        """
        rows = [_to_row(assertion) for assertion in assertions]
        if not rows:
            return
        statement = pg_insert(GraphAssertion).values([row.model_dump() for row in rows])
        await self._db.exec(statement.on_conflict_do_nothing(index_elements=["assertion_id"]))
        await self._db.flush()

    async def believed_at(self, user_id: str, moment: datetime) -> list[Assertion]:
        """Everything this person's graph held at ``moment``.

        Filtered in SQL rather than by loading the log and calling
        :meth:`~bacteria.app.graph.log.Assertion.believed_at`, because the log
        only grows and the believed set does not. The predicate is the same one,
        including the half-open close: an assertion superseded *at* ``moment`` was
        believed up to it and not at it, so a revision and the claim it replaces
        never both count.
        """
        statement = select(GraphAssertion).where(
            col(GraphAssertion.user_id) == user_id,
            col(GraphAssertion.recorded_at) <= moment,
            or_(
                col(GraphAssertion.recorded_until).is_(None),
                col(GraphAssertion.recorded_until) > moment,
            ),
        )
        rows = (await self._db.exec(statement)).all()
        return [_to_assertion(row) for row in rows]

    async def current(self, user_id: str) -> list[Assertion]:
        """Everything believed now — the common case, without inventing a ``now``.

        Separate from :meth:`believed_at` rather than a call to it with
        ``datetime.now``, because ``recorded_until IS NULL`` is an index-friendly
        predicate and because a caller passing a naive ``now()`` would compare
        local time against stored UTC and get a subtly wrong graph.
        """
        statement = select(GraphAssertion).where(
            col(GraphAssertion.user_id) == user_id,
            col(GraphAssertion.recorded_until).is_(None),
        )
        rows = (await self._db.exec(statement)).all()
        return [_to_assertion(row) for row in rows]

    async def supersede(self, closed: Assertion, replacement: Assertion) -> None:
        """Close belief in a claim and state the corrected one, together.

        Takes the pair :func:`~bacteria.app.graph.log.supersede` produced rather
        than computing it, so the decision about *what* the correction says stays
        in the pure layer where it can be tested without a database.

        ``recorded_until`` is the only column this class ever updates, and that is
        the whole of the append-only claim: the values in a row never change, and
        closing an interval is bookkeeping about a belief rather than an edit to
        what was claimed.

        Both writes are flushed, not committed. A caller that fails between this
        and its commit leaves neither — which matters more than usual here,
        because half of it is a log with a hole in it and the other half is a
        claim believed twice.
        """
        row = await self._db.get(GraphAssertion, closed.assertion_id)
        if row is None:
            raise UnknownAssertionError(closed.assertion_id)
        if row.user_id != closed.user_id:
            raise UnknownAssertionError(closed.assertion_id)
        row.recorded_until = closed.recorded_until
        self._db.add(row)
        self._db.add(_to_row(replacement))
        await self._db.flush()

    async def node_named(self, user_id: str, kind: str, label: str) -> Optional[Node]:
        """The node this person already has for this exact name, if any.

        Matched on the normalized label rather than the stored one, so the same
        name typed with different capitalization or Unicode composition finds the
        existing node instead of quietly creating a second.

        Normalizing in Python and comparing in SQL means the comparison happens
        over values the database never normalized itself. That is fine while
        `normalize` only casefolds and composes — both idempotent — and would
        stop being fine the moment it did anything a stored label could not be
        re-derived from. The stored label is the one that was written; this only
        decides which node it belongs to.
        """
        rows = (
            await self._db.exec(
                select(GraphNode).where(
                    col(GraphNode.user_id) == user_id,
                    col(GraphNode.kind) == kind,
                )
            )
        ).all()
        wanted = normalize(label)
        for row in rows:
            if normalize(row.label) == wanted:
                return _to_node(row)
        return None

    async def node(self, user_id: str, node_id: str) -> Optional[Node]:
        """One node by id, or ``None``. Scoped by owner like every other read."""
        row = await self._db.get(GraphNode, (user_id, node_id))
        return None if row is None else _to_node(row)

    async def mint_node(
        self,
        user_id: str,
        kind: str,
        label: str,
        *,
        now: datetime,
        node_id: Optional[str] = None,
    ) -> Node:
        """Record a thing nobody has mentioned before.

        No uniqueness constraint stops two nodes carrying the same name, and that
        is deliberate: two people really can share one, and the schema has no way
        to know which case it is looking at. Deciding they are the same is a claim
        somebody makes, not a rule a table enforces.

        ``node_id`` is supplied only for nodes whose identity is derived rather
        than allocated — the graph owner's, which comes from the user id so that
        two concurrent first mentions cannot produce two of them. Everything else
        leaves it alone and gets a fresh one.
        """
        node = Node(
            user_id=user_id,
            node_id=node_id or str(uuid.uuid4()),
            label=label,
            kind=kind,
            first_seen=now,
            last_seen=now,
        )
        self._db.add(
            GraphNode(
                user_id=node.user_id,
                node_id=node.node_id,
                label=node.label,
                kind=node.kind,
                first_seen=node.first_seen,
                last_seen=node.last_seen,
            )
        )
        await self._db.flush()
        return node

    async def touch_node(self, user_id: str, node_id: str, *, now: datetime) -> None:
        """Note that this thing came up again.

        ``last_seen`` is the only column on a node that changes. It answers "what
        has this person stopped talking about", which is a question about the
        record rather than about the world — so it is recorded time, and it is not
        a claim.
        """
        row = await self._db.get(GraphNode, (user_id, node_id))
        if row is None:
            raise UnknownNodeError(node_id)
        row.last_seen = now
        self._db.add(row)
        await self._db.flush()

    async def record_conclusion(self, conclusion: Conclusion) -> None:
        """Store a belief and the assertions it rests on.

        Evidence rows are written here rather than left to a caller, because a
        conclusion without them is the thing this layer exists to prevent: it
        would look like a belief and be unreachable from the assertion that
        supports it, so the staleness walk would silently skip it.
        """
        self._db.add(
            GraphConclusion(
                conclusion_id=conclusion.conclusion_id,
                user_id=conclusion.user_id,
                statement=conclusion.statement,
                confidence=conclusion.confidence,
                derived_by=conclusion.derived_by,
                status=conclusion.status,
                recorded_at=conclusion.recorded_at,
            )
        )
        for assertion_id in conclusion.evidence:
            self._db.add(
                GraphConclusionEvidence(
                    conclusion_id=conclusion.conclusion_id, assertion_id=assertion_id
                )
            )
        await self._db.flush()

    async def depending_on(self, user_id: str, assertion_ids: Sequence[str]) -> list[Conclusion]:
        """Every conclusion citing any of these assertions.

        The backwards walk, and the reason evidence is a table with an index on
        ``assertion_id`` rather than a JSON array on the conclusion. Drawing a
        conclusion needs its own evidence and could read a list happily; noticing
        that a revision undermined something requires going the other way, across
        all conclusions, which is a lookup rather than a scan.

        Returns conclusions with their *full* evidence, not just the matching
        ids, because a caller deciding what to do with a stale belief needs to see
        everything it rested on.
        """
        if not assertion_ids:
            return []

        matched = select(GraphConclusionEvidence.conclusion_id).where(
            col(GraphConclusionEvidence.assertion_id).in_(assertion_ids)
        )
        statement = select(GraphConclusion).where(
            col(GraphConclusion.user_id) == user_id,
            col(GraphConclusion.conclusion_id).in_(matched),
        )
        rows = (await self._db.exec(statement)).all()
        return [_to_conclusion(row, await self._evidence_for(row.conclusion_id)) for row in rows]

    async def set_status(self, user_id: str, conclusion_id: str, status: str) -> None:
        """Move a conclusion through its lifecycle.

        Scoped by owner like everything else, so a status change cannot reach
        across graphs even given a guessed id.
        """
        row = await self._db.get(GraphConclusion, conclusion_id)
        if row is None or row.user_id != user_id:
            raise UnknownConclusionError(conclusion_id)
        row.status = status
        self._db.add(row)
        await self._db.flush()

    async def _evidence_for(self, conclusion_id: str) -> list[str]:
        statement = select(GraphConclusionEvidence.assertion_id).where(
            col(GraphConclusionEvidence.conclusion_id) == conclusion_id
        )
        return list((await self._db.exec(statement)).all())


class UnknownAssertionError(KeyError):
    """An assertion id that did not resolve, or belongs to someone else.

    One error for both, deliberately, and for the same reason ``chat/access.py``
    returns 404 rather than 403: a caller that can tell "no such assertion" from
    "not yours" can enumerate the second by guessing.
    """


class UnknownConclusionError(KeyError):
    """A conclusion id that did not resolve, or belongs to someone else."""


class UnknownNodeError(KeyError):
    """A node id that did not resolve, or belongs to someone else."""
