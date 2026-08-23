"""Tables behind the memory graph.

Four tables, and the split is the same one ``chat/models.py`` makes: each
primary key states a rule, and the rules differ.

``graph_assertion`` is a **log**, keyed by a surrogate. That is the whole
difference between this and the schema ADR 0002 sketched, which keyed edges by
``(user_id, src, rel, dst)`` — a key that permits exactly one row per triple, so
a relation believed, retracted and believed again cannot be written down at all.
A log needs to hold every version of a claim; a current-state key forbids it.

``graph_node`` is **not** a log. A node is an identity, not a claim, and what is
said *about* it lives in assertions. Its two timestamps are recorded time only —
when this system first and last saw the thing — which is why nothing here gives
it valid time.

``graph_conclusion`` and ``graph_conclusion_evidence`` are separate tables rather
than a JSON list of assertion ids on the conclusion, because the query that
justifies the whole layer runs *backwards*: when an assertion is revised, find
every conclusion that leaned on it. A JSON array cannot serve that without a
scan, and the index it needs is the reason this is a join table.

Deliberately *not* ``MemoryContent`` subclasses. That base exists so the three
memory tables in ``chat`` share a column list, and
``test_every_memory_table_carries_the_same_content_columns`` enforces it. Nothing
here is a memory entry: an assertion is a claim with provenance, and a memory
entry is a confirmed fact a model is shown. Inheriting would make that test
assert something meaningless and would tie two schemas that change for different
reasons.
"""

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import Column, DateTime, UniqueConstraint
from sqlmodel import JSON, Field, SQLModel

OPEN_ENDED = datetime.max.replace(tzinfo=timezone.utc)
"""Valid time that has not ended: true as of now, and continuing.

A sentinel rather than ``'infinity'``, and this was measured rather than
reasoned about. Postgres accepts ``'infinity'::timestamptz`` and **psycopg 3
raises on the way back**: ``DataError: timestamp too large (after year 10K)``. It
does not degrade to ``datetime.max``; it refuses. A row carrying it would be
writable, correct in SQL, and fatal to every Python caller that selected it —
and nothing would notice until the first open-ended fact was read.

``datetime.max`` was checked against this stack instead: it round-trips to the
same value, compares greater than ``now()``, and orders correctly, so indexes and
``ORDER BY`` behave. ``tests/test_graph_models.py`` is what keeps that true.

What it costs: a fact genuinely valid until the year 9999 is indistinguishable
from an open one. Every query anyone will write treats those identically, which
is why this is acceptable rather than merely tolerated.

Distinct from ``None``, which means *unknown* — see :class:`GraphAssertion`.
"""

ALWAYS = datetime.min.replace(tzinfo=timezone.utc)
"""Valid time with no beginning: true for as long as the subject existed.

The mirror of :data:`OPEN_ENDED` and much rarer — most facts started at some
unrecorded moment, which is ``None``, not this. Reach for it only when "has
always been true" is a claim someone actually made.
"""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _tz_column(nullable: bool = False) -> Column:
    """A timestamp that keeps its timezone on the way back.

    Same reasoning as ``chat/models.py``: a naive datetime compares as local
    time and the difference is invisible until it is a bug. Nullable here where
    ``chat``'s is not, because half the columns in this schema use ``NULL`` to
    mean *unknown* and need to be able to hold it.
    """
    return Column(DateTime(timezone=True), nullable=nullable)


class GraphNode(SQLModel, table=True):
    """One thing the graph knows about. An identity, not a claim.

    Keyed by ``(user_id, node_id)``. The owner is part of the key rather than a
    column beside it, so a query that forgets to scope by user cannot compile
    into something that returns another person's graph — which is the failure
    ADR 0004 warns about and `chat/access.py` records having already happened
    once, in ingestion.

    ``node_id`` is minted by whatever creates the node and is stable forever,
    because every assertion references it. Two nodes that turn out to be the
    same person are **not** merged: an assertion links them, both survive, and
    the merge is retractable. That is why nothing here has a "merged into"
    column.

    ``first_seen`` and ``last_seen`` are recorded time — when this system saw the
    thing, not when it existed. A node has no valid time at all: what was true
    *about* it, and when, is what assertions are for.
    """

    __tablename__ = "graph_node"

    user_id: str = Field(primary_key=True)
    node_id: str = Field(primary_key=True)
    label: str
    kind: str
    attrs: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    first_seen: datetime = Field(default_factory=_utcnow, sa_column=_tz_column())
    last_seen: datetime = Field(default_factory=_utcnow, sa_column=_tz_column())


class GraphAssertion(SQLModel, table=True):
    """One claim about the world, with when it was true and when we believed it.

    **Two time axes, and both are load-bearing.** ``valid_from``/``valid_to`` say
    when the claim held in the world; ``recorded_at``/``recorded_until`` say when
    this system held it. Only the second answers "what did we believe last
    Tuesday", because filtering today's beliefs to a past valid interval returns
    what we think *now* about Tuesday. The agent's ADR 0020 replays past runs, and
    with one axis that evaluation does not fail — it grades the wrong thing.

    Valid time can sometimes be recovered later from testimony. **Recorded time
    cannot be backfilled at all**, which is why it is here before there are rows.

    **Each valid bound has three states, not two.** A timestamp is a known date;
    :data:`OPEN_ENDED` (or :data:`ALWAYS`) means the interval genuinely has no
    end (or beginning); ``None`` means *unknown*. Collapsing open into unknown is
    the mistake this column shape exists to prevent — "she is their CTO" and "she
    was mentioned as CTO" are different facts, and only the first says the claim
    still holds. Open means true as of now, so two open-ended intervals provably
    overlap however unknown their starts, which is what makes a contradiction
    between two current claims decidable.

    ``None`` also gives constraint evaluation its third answer for free, since
    ``NULL <= now()`` is unknown rather than false. Satisfied, violated, and
    *undecidable* are the three outcomes, and the third is a state to render
    rather than an error to raise.

    **Nothing here is ever edited except ``recorded_until``.** Revising a fact
    appends a new row and closes the old one's recorded interval; the values in a
    row never change. Closing the interval is bookkeeping about a belief, not an
    overwrite of what was claimed.

    Current graph is ``recorded_until IS NULL``. Belief at ``T`` is
    ``recorded_at <= T AND (recorded_until IS NULL OR recorded_until > T)``.

    ``trust`` records what kind of source this came from, and it gates influence
    rather than storage: a claim from third-party text is stored exactly like any
    other and may not affect which memories are surfaced. Nothing in any tier
    reaches a model unconfirmed.

    ``session_id`` is provenance and deliberately **not** a foreign key, unlike
    ``chat``'s own tables. A pointer that must resolve is a claim about
    referential integrity this does not want to make: an assertion may later come
    from ingestion, or from a source with no session at all, and the column
    should be able to say so by being empty rather than by being dropped.

    The unique constraint is what makes a re-run idempotent — the same claim
    recorded at the same instant is the same row — while still permitting the
    same triple to be believed, retracted and believed again at different times.
    """

    __tablename__ = "graph_assertion"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "src", "rel", "dst", "recorded_at", name="uq_assertion_claim_recorded"
        ),
    )

    assertion_id: str = Field(primary_key=True)
    user_id: str = Field(index=True)
    src: str
    rel: str
    dst: str
    attrs: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))

    valid_from: Optional[datetime] = Field(default=None, sa_column=_tz_column(nullable=True))
    valid_to: Optional[datetime] = Field(default=None, sa_column=_tz_column(nullable=True))

    recorded_at: datetime = Field(default_factory=_utcnow, sa_column=_tz_column())
    recorded_until: Optional[datetime] = Field(default=None, sa_column=_tz_column(nullable=True))

    trust: str
    session_id: Optional[str] = Field(default=None, index=True)
    run_id: Optional[str] = Field(default=None, index=True)


class GraphConclusion(SQLModel, table=True):
    """A belief the system drew rather than was told.

    A separate table from ``chat_memory_proposal``, and the reasons are the same
    kind the memory tables give for their own split. A proposal's lifecycle is
    terminal — proposed, then activated or rejected — and has no ``stale``, which
    is the state that justifies this layer existing: when the evidence under a
    conclusion is retracted, the conclusion is not wrong, it is unsupported.
    Proposals are keyed ``(session_id, source, key)`` and overwrite so a re-run is
    idempotent, where two conclusions about one subject are both legitimate and a
    superseded one must survive. And a proposal belongs to a conversation, where a
    conclusion is about entities and is still a belief in the next one.

    ``derived_by`` names what produced it, and the distinction it carries is not
    human-versus-machine. A deterministic rule can still be **defeasible** — "she
    became CTO when he left" follows from a constraint and a known boundary, and
    the same data is equally consistent with a gap. Entailed things are derived
    and recomputed silently; assumed things are conclusions and carry evidence.

    An assumed value never enters :class:`GraphAssertion`. It stays here, in the
    conclusion that assumed it, so that the assumption is visible where it
    matters, retraction has nothing to un-write, and the next inference cannot
    read a guess as an observation.

    Nothing here reaches a model. Accepting a conclusion writes an ordinary
    memory entry carrying its prose, which is what a human confirmed — see the
    agent's ADR 0017.
    """

    __tablename__ = "graph_conclusion"

    conclusion_id: str = Field(primary_key=True)
    user_id: str = Field(index=True)
    statement: str
    confidence: float
    derived_by: str
    status: str = Field(default="active", index=True)
    recorded_at: datetime = Field(default_factory=_utcnow, sa_column=_tz_column())


class GraphConclusionEvidence(SQLModel, table=True):
    """Which assertions a conclusion rests on.

    A join table rather than a list on the conclusion, because the question that
    matters is asked backwards. Drawing a conclusion needs its own evidence and
    could read a JSON array happily; **revising an assertion needs every
    conclusion that cited it**, and that is a lookup by ``assertion_id`` across
    all conclusions. Hence the index, which is the whole reason this is a table.

    Both sides are foreign keys, unlike ``session_id`` on an assertion. These are
    references within one feature to rows that must exist — an evidence link to a
    missing assertion is not incomplete provenance, it is a broken conclusion.
    """

    __tablename__ = "graph_conclusion_evidence"

    conclusion_id: str = Field(foreign_key="graph_conclusion.conclusion_id", primary_key=True)
    assertion_id: str = Field(
        foreign_key="graph_assertion.assertion_id", primary_key=True, index=True
    )
