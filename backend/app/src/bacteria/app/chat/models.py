"""Tables behind the agent's session state.

Three tables, not one, mirroring the split the agent insists on: transcript,
working state, and memory have different lifecycles, and a single JSON blob per
session would merge them back together in storage even while the code kept them
apart. Transcript is append-only rows; memory is keyed rows that are overwritten
and deleted; working state is per-session scratch and lives on the session row.

Payloads are stored as JSON columns rather than modelled further. A transcript
item's payload shape depends on its ``kind`` and is the agent's business, not
this schema's — normalizing it here would mean this application had opinions
about what a tool call looks like, and would need a migration every time the
agent gained a new kind of event.
"""

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import Column, DateTime, UniqueConstraint
from sqlmodel import JSON, Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# SQLite drops timezone information on the way in and hands back naive
# datetimes, which then compare as if they were local time. Storing with an
# explicit timezone-aware column keeps round trips honest on backends that
# support it; see `_as_utc` in repository.py for the read side.
def _tz_column() -> Column:
    return Column(DateTime(timezone=True), nullable=False)


class MemoryContent(SQLModel):
    """What every memory row holds, whatever owns it.

    A non-table base. The three tables below stay three tables with three
    primary keys — the keys *are* the rules each one states (ADR 0021), and the
    only thing that was ever duplicated is the column list. So each table
    declares its own identity and inherits what they all say.

    Adding a field here adds it to all three, which is the point: the lifecycle
    work will want an ``expires_at``, and adding it to two of three is the
    plausible mistake — the omitted one would be user-scoped memory, where
    expiry matters most.

    ``sa_type`` rather than ``sa_column``, and that is not a style preference. A
    ``Column`` is an instance bound to one ``Table``; three subclasses
    inheriting a single one would fight over which table owns it.
    """

    value: dict[str, Any] = Field(default_factory=dict, sa_type=JSON, nullable=True)
    reason: str
    # `sa_type` is annotated as taking a type, and this passes an instance,
    # because the timezone flag is an argument to the type rather than part of
    # it. SQLAlchemy accepts either; SQLModel's signature does not say so. The
    # rendered DDL was diffed against the previous `sa_column=_tz_column()`
    # form and is identical — `TIMESTAMP WITH TIME ZONE NOT NULL`.
    created_at: datetime = Field(
        default_factory=_utcnow,
        sa_type=DateTime(timezone=True),  # ty: ignore[invalid-argument-type]
    )


class ChatSession(SQLModel, table=True):
    """One conversation. The row the other two tables hang off.

    ``user_id`` is a plain column and not a foreign key: the agent's notion of a
    user is "whoever owns this session", and binding it to an accounts table
    would make the agent's storage depend on a feature it knows nothing about.
    """

    __tablename__ = "chat_session"

    session_id: str = Field(primary_key=True)
    user_id: str = Field(index=True)
    created_at: datetime = Field(default_factory=_utcnow, sa_column=_tz_column())
    working_state: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))


class ChatTranscriptItem(SQLModel, table=True):
    """One entry in the durable record. Append-only.

    ``seq`` orders the transcript explicitly rather than relying on ``id`` or on
    ``timestamp``. Autoincrement ordering is an implementation detail that a
    different backend may not preserve, and two items committed in the same turn
    can share a timestamp to the microsecond.

    Unique per session, and that constraint is doing real work rather than
    documenting an assumption. ``commit`` computes the next ``seq`` from the
    current maximum, so before it took a row lock two overlapping commits both
    claimed the same position — and nothing objected, because a duplicate
    ``seq`` still reads back as a perfectly ordinary transcript. The lock is the
    fix; this is what makes a future regression fail loudly instead of quietly
    reordering someone's conversation.

    ``run_id`` groups the items one turn wrote. Indexed because the question it
    answers — "show me everything that run produced" — is the one asked when a
    caller reports a bad turn and quotes the id the API gave them. Nullable, and
    permanently so: rows predating the column named no run, and no backfill can
    invent one. See bacteria's ADR 0018.
    """

    __tablename__ = "chat_transcript_item"
    __table_args__ = (UniqueConstraint("session_id", "seq", name="uq_transcript_session_seq"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    session_id: str = Field(foreign_key="chat_session.session_id", index=True)
    seq: int = Field(index=True)
    run_id: Optional[str] = Field(default=None, index=True)
    kind: str
    payload: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    timestamp: datetime = Field(default_factory=_utcnow, sa_column=_tz_column())


class ChatMemoryEntry(MemoryContent, table=True):
    """One active fact — something the model is told on every later turn.

    ``value`` is wrapped in a JSON object rather than stored bare, because a
    memory's value may be any JSON type — including ``null``, a string, or a
    number — and a bare JSON column cannot distinguish "stored null" from "no
    row" on every backend.

    ``source`` records who suggested it and survives activation, so a memory
    that came from a background extractor can still be distinguished from one
    the owner wrote. It is deliberately *not* part of the primary key: at most
    one active fact may claim a key, whatever proposed it, because the model
    would otherwise be handed two answers and told nothing about which is
    current.
    """

    __tablename__ = "chat_memory_entry"

    session_id: str = Field(foreign_key="chat_session.session_id", primary_key=True)
    key: str = Field(primary_key=True)
    source: str


class ChatUserMemoryEntry(MemoryContent, table=True):
    """One active fact belonging to a person rather than to a conversation.

    A third table rather than a ``scope`` column on ``chat_memory_entry``, and
    the primary key is again the reason: this is keyed by ``(user_id, key)``,
    where session memory is keyed by ``(session_id, key)``. Those are different
    uniqueness rules over different owning entities, and one table would have to
    hold a nullable ``session_id``, a nullable ``user_id``, and a check
    constraint asserting exactly one is set — encoding in a constraint what two
    primary keys state outright.

    It also keeps the leakage question answerable by looking at a query rather
    than at a filter: rows here are selected by ``user_id`` and nothing else, so
    "could one person see another's memory" is a question about one join.

    There is deliberately no foreign key to a users table. ``user_id`` is the
    authenticated principal, which this application does not own a table for —
    the same identifier ``chat_session.user_id`` already carries unconstrained.
    Adding one here would invent an ownership this schema does not have.
    """

    __tablename__ = "chat_user_memory_entry"

    user_id: str = Field(primary_key=True)
    key: str = Field(primary_key=True)
    source: str


class ChatMemoryExtraction(SQLModel, table=True):
    """How far the memory extractor has read this session's transcript.

    Not a ``MemoryContent`` subclass: this holds no memory. It is bookkeeping for
    the job that *produces* memory, and it lives here rather than as a column on
    ``chat_session`` because a session is not the extractor's business — a second
    reader of the transcript would want its own watermark, and a column named for
    one of them would be the wrong shape immediately.

    ``through_seq`` is the highest transcript ``seq`` already examined, so the
    extractor reads ``seq > through_seq`` and its cost stays proportional to new
    turns rather than to conversation length. Initialized to ``-1`` rather than
    ``0``, matching the ``coalesce(max(seq), -1)`` in ``commit``: position ``0``
    is a real item, so ``0`` would silently skip the first message of every
    session.

    Deliberately *not* locked across a run, unlike the session row in ``commit``.
    A run holds a model call in the middle of it, and a row lock spanning a
    multi-second network round trip is a lock held for as long as a vendor feels
    like taking. Two mechanisms replace it, and both are properties of data
    rather than of timing:

    - the watermark only ever moves forward (``GREATEST`` on write), so a slow
      run cannot rewind a fast one;
    - proposals are keyed by ``(source, key)`` and overwrite, so a duplicated run
      rewrites its own suggestions instead of accumulating them — which is
      exactly the idempotence the agent's ADR 0017 said would make a background
      proposer safe to retry where ingestion is not.

    What this costs is that two concurrent runs may both pay for a model call and
    reach the same answer. That is money, not correctness, and it is the cheaper
    of the two mistakes available here.
    """

    __tablename__ = "chat_memory_extraction"

    session_id: str = Field(foreign_key="chat_session.session_id", primary_key=True)
    through_seq: int = Field(default=-1)
    updated_at: datetime = Field(default_factory=_utcnow, sa_column=_tz_column())


class ChatMemoryProposal(MemoryContent, table=True):
    """One suggested fact, which no model can see until a human activates it.

    A separate table rather than a ``status`` column on the one above, and the
    reason is the primary key. Proposals are keyed by ``(source, key)`` so two
    proposers may both suggest ``tone`` without either silently overwriting the
    other; active memories are keyed by ``key`` alone. Those are different
    uniqueness rules, and one table would have to express the stricter one as a
    partial unique index — a constraint that holds only for some rows, which is
    exactly the kind of rule that is easy to write and easy to drop later
    without noticing.

    Two tables let each primary key state its own rule, and make "reaches the
    model" a question of which table a row is in rather than of a column
    someone must remember to filter on. See ADR 0017.
    """

    __tablename__ = "chat_memory_proposal"

    session_id: str = Field(foreign_key="chat_session.session_id", primary_key=True)
    source: str = Field(primary_key=True)
    key: str = Field(primary_key=True)
