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

from bacteria.app.graph.temporal import ALWAYS, OPEN_ENDED

__all__ = [
    "ALWAYS",
    "OPEN_ENDED",
    "GraphAssertion",
    "GraphConclusion",
    "GraphConclusionEvidence",
    "GraphExtraction",
    "GraphNode",
]
"""Re-exports the two temporal sentinels, which are defined in ``temporal.py``.

They were declared here first, when this was the only module in the package, and
moved once there was logic to compare them: what a bound *means* is a property of
the domain, not of the table it is stored in, and the comparison rules in
``temporal.py`` depend on ``OPEN_ENDED`` being the maximum. Anything that stores
an assertion needs both, so both stay importable from here.
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
    ontology: Optional[str] = Field(default=None, index=True)
    """Which model this node belongs to, or ``NULL`` for the owner's memory.

    A partition, kept apart from ``user_id`` on purpose. That column answers
    *whose* and every query already filters on it; this one answers *which
    model*, and the two stopped coinciding the moment a second ontology existed.
    Folding an architecture model into ``user_id`` would have made one column
    mean a person on some rows and a project on others -- and left nowhere to
    record who stated a claim, since the person was only ever implied by it.

    ``NULL`` rather than a sentinel so that every row written before this
    existed keeps its meaning without being rewritten, which is the backfilling
    the log forbids.
    """

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
    ontology: Optional[str] = Field(default=None, index=True)
    """Which model this claim belongs to; ``NULL`` is the owner's memory."""

    stated_by: Optional[str] = Field(default=None)
    """The principal who said it, where anybody did.

    ``trust`` records *how* a claim arrived and nothing recorded *who believes
    it*, which is invisible in a graph with one owner and the first question
    anybody asks of a shared one. Added now rather than later because a row
    written unattributed can never be attributed afterwards -- inventing an
    author for an existing row is exactly the false history this log forbids.

    Nullable, and the nulls are honest: nobody was recorded for the rows written
    before this column, and pretending otherwise would be the same lie.
    """

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

    origin: str = Field(default="inferred", index=True)
    """Whether anybody meant this, as against how it arrived.

    ``stated`` when the owner said it, ``inferred`` when something worked it out.
    ``trust`` answers a different question and was never asked this one: it
    records which *channel* a claim came through, and after the first turn
    essentially every transcript slice contains an assistant message, so the tier
    reads ``third-party`` whoever was speaking.

    *Which channel* and *did anyone mean it* come apart exactly where it matters.
    A projection has to answer the second before it may speak, which is why this
    is a column and not an implication of which table a row is in.

    Indexed because the projection filters on it on every read.
    """

    scope: str = Field(default="user")
    """Where a claim applies, as against where it came from.

    ``user`` everywhere, ``session`` only within the conversation named by
    ``session_id``. The existing column answers provenance and cannot answer
    this: a fact learned in one conversation usually applies to all of them.

    Together the pair reproduces the agent's own session/user memory scopes
    without inventing a third concept.
    """

    closed_by: Optional[str] = Field(default=None)
    """Which act ended belief in this claim, or ``None`` while it is believed.

    ``superseded`` when a correction replaced it, ``retracted`` when a person
    said it should not be believed. Both set ``recorded_until`` and nothing else
    told them apart — recoverable only by checking whether a same-triple
    assertion appeared at the same instant, which is fragile and would stop
    working silently the moment anything else wrote at that instant.

    The distinction is what makes a rejection a *recorded fact* rather than an
    absence, which is the property ADR 0009 rests on and the reason this is a
    column rather than something inferred at read time.

    No companion actor column. In a personal graph the only thing that may
    retract is the owner, and a column that can hold exactly one value records
    nothing. That changes when a graph has more than one writer.
    """


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


class GraphExtraction(SQLModel, table=True):
    """How far the graph extractor has read this session's transcript.

    A second watermark table beside ``chat_memory_extraction``, which is what
    that table's own docstring said would happen: "a second reader of the
    transcript would want its own watermark, and a column named for one of them
    would be the wrong shape immediately". This is that second reader.

    Two watermarks rather than one shared column, because the readers advance
    independently and for different reasons. Turning graph extraction on for an
    existing deployment must not skip the backlog just because memory extraction
    has already been through it, and a prompt change that justifies re-reading
    one does not justify re-reading the other.

    ``through_seq`` is the highest transcript ``seq`` already examined, so a run
    reads ``seq > through_seq`` and costs stay proportional to new turns rather
    than to conversation length. Initialized to ``-1`` rather than ``0``, since
    position ``0`` is a real item and a default of ``0`` would silently skip the
    first message of every session — the one most likely to say who someone is.

    Not locked across a run, for the reason ``ChatMemoryExtraction`` gives: a run
    holds a model call in the middle of it, and a row lock spanning a network
    round trip is held for as long as a vendor feels like taking. Two concurrent
    runs may both pay for a call and reach the same answer, which is money rather
    than correctness.

    **The foreign key is the part that does not generalize.** ``graph_assertion``
    deliberately refuses one on its own ``session_id`` so that a claim may come
    from ingestion, or from no session at all; this table takes one, so a source
    that is not a conversation has nowhere to record how far it has been read.
    That is the first thing to move when a second source arrives, and
    :func:`~bacteria.app.personal.claim_extraction.extract_assertions` carries the rest of
    the list.
    """

    __tablename__ = "graph_extraction"

    session_id: str = Field(foreign_key="chat_session.session_id", primary_key=True)
    through_seq: int = Field(default=-1)
    updated_at: datetime = Field(default_factory=_utcnow, sa_column=_tz_column())
