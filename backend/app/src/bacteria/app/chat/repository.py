"""A durable implementation of the agent's ``SessionRepository``.

This is the whole point of the protocol the agent declares: the runtime holds
one of these instead of the in-memory store and does not notice. Nothing in
``bacteria`` imports this module, this package, or SQLModel.

The protocol's behavioral guarantees are the ones worth being careful about,
because no type checker enforces them. Two matter here:

*Reads are detached.* ``get_state`` returns dataclasses built from rows, never
ORM objects. Handing back a SQLModel instance would give the caller a live
handle on a database row — mutating it and committing anything afterwards would
write, which is precisely the "state edited from outside the layer that owns it"
that the agent's copy-on-read exists to prevent. Constructing plain dataclasses
is not a conversion nicety; it is that invariant.

*Commit appends.* Transcript items are inserted with an increasing ``seq``;
working state is merged key by key. Neither replaces what is there.

*Commits to one session are serialized.* ``commit`` takes a row lock on the
session before computing the next ``seq``, and a unique constraint on
``(session_id, seq)`` catches anything that gets past it. This was a live bug,
not a precaution: five concurrent commits all claimed position 0, and two-item
commits interleaved so that a turn's question and its answer were pulled apart
by other turns.

Not built:
    Pagination. ``get_state`` loads the entire transcript, which is bounded only
    by how long a conversation runs. The agent's context assembly windows what
    it sends to a model, so this is a memory and latency cost rather than a
    correctness one — until a conversation is long enough for it not to be.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional, cast

from sqlalchemy import func
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from bacteria.agent.session.store import (
    OWNER,
    SESSION_SCOPE,
    MemoryEntry,
    MemoryScope,
    Session,
    SessionState,
    TranscriptItem,
    TranscriptItemKind,
    UnknownSessionError,
)
from bacteria.app.chat.memory import MemoryStore, TableMemoryStore
from bacteria.app.chat.models import (
    ChatMemoryEntry,
    ChatMemoryExtraction,
    ChatMemoryProposal,
    ChatSession,
    ChatTranscriptItem,
    ChatUserMemoryEntry,
)
from bacteria.app.core.settings import get_settings


@dataclass(frozen=True)
class SessionSummary:
    """One line in a session picker: enough to choose, and nothing more.

    Deliberately not a :class:`~bacteria.agent.session.store.Session`. That type
    is the agent's and carries ``user_id``, which every row here already shares —
    a listing is by definition all one principal's, so repeating the owner on
    each line would be noise that also reads like it could vary.

    ``last_activity_at`` falls back to ``created_at`` for a session nobody has
    spoken in. ``None`` would be more literal and would force every caller to
    handle a sort key that is sometimes absent, to distinguish a case that looks
    identical on screen.
    """

    session_id: str
    created_at: datetime
    last_activity_at: datetime


@dataclass(frozen=True)
class ExtractionProgress:
    """Whether memory extraction has kept up with a conversation.

    Answerable before this existed only by reading ``chat_memory_extraction`` by
    hand, which is how it was answered during the deployment where no worker was
    running: the symptom was proposals never appearing, and the evidence was a
    watermark that had stopped moving while the transcript grew.

    Attributes:
        through_seq: Highest transcript position already examined. ``-1`` when
            extraction has never run, matching the column's own initial value.
        latest_seq: Highest position in the transcript. ``-1`` when empty.
        behind: How many positions are unexamined. Zero means caught up; it is
            zero for an empty session too, which is correct rather than a
            special case — nothing is waiting to be read.
    """

    through_seq: int
    latest_seq: int
    behind: int


@dataclass(frozen=True)
class KnownKeys:
    """The key vocabulary a conversation has, split by whether a human confirmed it.

    Two sets rather than one, because they carry different authority. ``active``
    keys were chosen by a person activating a proposal, which makes them the
    canonical name for a fact as far as this system knows. ``proposed`` keys are
    guesses nobody has ruled on yet — useful for consistency across runs and no
    evidence of anything.

    Disjoint: a key that is both is reported as active only. See
    :meth:`SqlSessionRepository.known_keys` for why the distinction exists.
    """

    active: frozenset[str] = frozenset()
    proposed: frozenset[str] = frozenset()

    def __bool__(self) -> bool:
        return bool(self.active or self.proposed)


def _as_utc(value: datetime) -> datetime:
    """Reattach UTC to a datetime a backend handed back without one.

    A no-op against Postgres, which returns what ``DateTime(timezone=True)``
    promises. It was written for SQLite, which ignores that flag and returns
    naive values that would then be compared as local time.

    Kept rather than deleted along with the SQLite support, because this is the
    boundary where stored rows become the plain dataclasses the agent sees, and
    an aware datetime is part of what that hand-off promises.

    Worth knowing how the difference was found. Only `chat/` ever had this
    helper — `ingestion/` did not, so its timestamps genuinely were naive under
    test and aware in production. A workaround present in one feature and absent
    in another is what an untestable backend difference looks like from inside.
    """
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _configured_store(session: AsyncSession) -> MemoryStore:
    """The store this deployment chose, defaulting to the tables that work.

    Read here rather than at every call site, so that "which memory is in use" is
    one answer for the process rather than a thing each caller could get
    differently -- which is the property that makes a discrepancy between the two
    attributable to the stores rather than to the caller.
    """
    if get_settings().graph_backed_memory:
        # Imported here rather than at module scope: the graph store imports the
        # graph package, which imports this one for its own models, and a
        # top-level import would close the cycle.
        from bacteria.app.chat.graph_memory import GraphMemoryStore

        return GraphMemoryStore(session)
    return TableMemoryStore(session)


class SqlSessionRepository:
    """Stores agent sessions in a relational database.

    Satisfies :class:`bacteria.agent.session.protocol.SessionRepository` structurally.

    Genuinely async, not merely async-shaped: the session is an
    :class:`~sqlmodel.ext.asyncio.session.AsyncSession` and every query is
    awaited, so a request waiting on the database does not hold the event loop.
    An earlier version had these methods ``async`` around synchronous calls,
    which satisfied the protocol and delivered none of the benefit.

    Args:
        session: An open database session. Injected rather than created here,
            so that transaction scope belongs to whoever knows what a unit of
            work is — for a request, that is the dependency that opened it.
    """

    def __init__(self, session: AsyncSession, memory: Optional[MemoryStore] = None) -> None:
        self._db = session
        # Defaulted rather than required, so every existing call site is
        # unchanged and the seam costs nothing to ignore. A caller that wants the
        # graph's memory passes one; ADR 0010 puts that choice in configuration
        # rather than per request, because a store chosen per call makes "which
        # memory answered" unanswerable exactly when the two disagree.
        self._memory: MemoryStore = memory or _configured_store(session)

    @property
    def session(self) -> AsyncSession:
        """The session this reads through, for composing another reader on it.

        Exposed rather than threaded through ``run_turn``'s signature, and that
        is a trade rather than a clean answer. The alternative was passing the
        database into a function that already takes the repository built from it,
        or building the reader in an entrypoint -- and this codebase's rule is
        that a decision made in an entrypoint is a decision nothing tests.

        Read-only, and for readers only. Anything that writes through this rather
        than through a method here is outside the detached-read guarantee the
        module docstring makes.
        """
        return self._db

    async def create_session(self, user_id: str) -> Session:
        row = ChatSession(session_id=str(uuid.uuid4()), user_id=user_id)
        self._db.add(row)
        await self._db.commit()
        await self._db.refresh(row)
        return Session(
            session_id=row.session_id,
            user_id=row.user_id,
            created_at=_as_utc(row.created_at),
        )

    async def list_sessions(self, user_id: str) -> list["SessionSummary"]:
        """Every session this principal owns, most recently active first.

        **The one session route with no session id to check**, which makes it
        the one place `chat/access.py` cannot help. Ownership here is the
        ``WHERE`` clause rather than a comparison after loading, so a bug is a
        missing filter and not a missing check — and a missing filter returns
        other people's conversations rather than failing closed. That asymmetry
        is why this method takes ``user_id`` and not a session id, and why the
        route hands it :attr:`Principal.id` and nothing the client sent.

        Sorted by last activity, not by creation. A picker ordered by creation
        puts a conversation someone abandoned in January above the one they were
        in five minutes ago.

        Returns:
            Summaries, not states. Loading each session's transcript to build a
            list would read the whole history of every conversation to render
            one line each — the cost this class's "Not built: Pagination" note
            is about, paid on the cheapest screen in the product.
        """
        # `timestamp`, which is what a transcript item calls the moment it
        # happened -- there is no `created_at` on that table, and reaching for
        # the name every other table uses is how this was first written.
        last_activity = func.coalesce(
            func.max(ChatTranscriptItem.timestamp), ChatSession.created_at
        )
        rows = (
            await self._db.exec(
                select(ChatSession.session_id, ChatSession.created_at, last_activity)
                .outerjoin(
                    ChatTranscriptItem,
                    col(ChatTranscriptItem.session_id) == col(ChatSession.session_id),
                )
                .where(ChatSession.user_id == user_id)
                .group_by(col(ChatSession.session_id), col(ChatSession.created_at))
                .order_by(last_activity.desc())
            )
        ).all()

        # Unpacked positionally rather than by attribute: a `select` of columns
        # yields plain tuples, and naming them with `.label()` satisfies neither
        # the type checker nor a reader looking for where the names came from.
        return [
            SessionSummary(
                session_id=session_id,
                created_at=_as_utc(created_at),
                last_activity_at=_as_utc(last_activity_at),
            )
            for session_id, created_at, last_activity_at in rows
        ]

    async def extraction_progress(self, session_id: str) -> "ExtractionProgress":
        """How far memory extraction has read this session, and how far behind.

        ``behind`` is computed here rather than left to the caller because the
        subtraction has a trap in it: both values start at ``-1``, not ``0``, so
        a client doing the arithmetic on a fresh session gets the right answer
        only by accident and a client special-casing zero gets it wrong.

        The ceiling query is the same one ``chat.extraction._max_seq`` runs, and
        the duplication is deliberate. That one executes inside the extractor's
        own transaction, where *when* it is read is part of the concurrency
        argument that module makes at length; this one is a detached read for a
        reader. Sharing them would tie a reporting route to a locking decision.
        """
        watermark = await self._db.get(ChatMemoryExtraction, session_id)
        through_seq = watermark.through_seq if watermark is not None else -1

        latest_seq = (
            await self._db.exec(
                select(func.coalesce(func.max(ChatTranscriptItem.seq), -1)).where(
                    ChatTranscriptItem.session_id == session_id
                )
            )
        ).one()

        return ExtractionProgress(
            through_seq=through_seq,
            latest_seq=latest_seq,
            behind=latest_seq - through_seq,
        )

    async def get_state(self, session_id: str) -> SessionState:
        row = await self._require(session_id)

        items = (
            await self._db.exec(
                select(ChatTranscriptItem)
                .where(ChatTranscriptItem.session_id == session_id)
                # SQLModel declares `seq: int`, so a checker sees the value type
                # where SQLAlchemy passes the column descriptor. Every ordering
                # and filtering expression in this file has the same shape.
                .order_by(ChatTranscriptItem.seq)  # ty: ignore[invalid-argument-type]
            )
        ).all()
        # Through the port, so that where a keyed memory comes from is a choice
        # rather than a fact about this class. `row.user_id` comes from the
        # session already loaded above, which the route has checked the caller
        # owns -- the store is told rather than looking it up, so there is one
        # place that decision is made.
        remembered = await self._memory.entries(session_id, row.user_id)

        # Plain dataclasses, never the ORM rows themselves. See the module
        # docstring: this is the detached-read guarantee, not a formality.
        return SessionState(
            session=Session(
                session_id=row.session_id,
                user_id=row.user_id,
                created_at=_as_utc(row.created_at),
            ),
            transcript=[
                TranscriptItem(
                    # Cast, not validated. The column is `str` and the dataclass
                    # wants a closed `Literal`, so something has to bridge them,
                    # and rejecting an unrecognized kind would be the wrong
                    # bridge: during a rolling deploy an old reader meets rows a
                    # new writer produced, and raising there turns a benign
                    # version skew into a session nobody can read. Passing it
                    # through is harmless — every consumer selects the kinds it
                    # knows and ignores the rest.
                    kind=cast(TranscriptItemKind, item.kind),
                    payload=dict(item.payload),
                    timestamp=_as_utc(item.timestamp),
                    run_id=item.run_id,
                )
                for item in items
            ],
            working_state=dict(row.working_state),
            memory=remembered.memory,
            user_memory=remembered.user_memory,
            proposals=remembered.proposals,
        )

    async def commit(
        self,
        session_id: str,
        new_transcript_items: Optional[list[TranscriptItem]] = None,
        working_state_updates: Optional[dict[str, Any]] = None,
    ) -> None:
        # Locks the session row, and everything below depends on it. `seq` is
        # computed from the current maximum, so two commits that both read
        # before either writes claim the same position -- and the column that
        # exists to order the transcript stops ordering it, silently, because
        # the result still reads back cleanly.
        #
        # Reproduced before it was fixed: five concurrent commits all took
        # position 0, and three two-item commits interleaved into
        # ['x-a', 'y-a', 'z-a', 'x-b', 'y-b', 'z-b'] -- a turn's question and
        # its answer pulled apart by other turns.
        #
        # The lock is on the session row rather than the item table because
        # ordering is per session: two different conversations have no reason to
        # wait for each other. It is released when this transaction ends, which
        # is the `commit()` below.
        row = await self._require(session_id, lock=True)

        next_seq = (
            await self._db.exec(
                select(func.coalesce(func.max(ChatTranscriptItem.seq), -1)).where(
                    ChatTranscriptItem.session_id == session_id
                )
            )
        ).one() + 1
        for offset, item in enumerate(new_transcript_items or []):
            self._db.add(
                ChatTranscriptItem(
                    session_id=session_id,
                    seq=next_seq + offset,
                    kind=item.kind,
                    payload=item.payload,
                    timestamp=item.timestamp,
                    run_id=item.run_id,
                )
            )

        if working_state_updates:
            # Rebound rather than mutated in place: SQLAlchemy does not track
            # mutations inside a plain JSON column, so `row.working_state[k] = v`
            # updates the object in memory and writes nothing.
            row.working_state = {**row.working_state, **working_state_updates}
            self._db.add(row)

        await self._db.commit()

    async def known_keys(self, session_id: str) -> KnownKeys:
        """Every key this conversation's memory already uses, split by standing.

        Exists for the extractor, and for one specific failure. A key is chosen
        by a model, and left to itself the model chooses a new one every run: the
        same fact arrived as ``name``, ``first_name``, ``preferred_name`` and
        ``nickname`` across four extractions of one conversation. Proposals are
        keyed by ``(source, key)``, so those do not overwrite each other -- they
        accumulate, and a review queue fills with one fact wearing four names.

        Showing the model what already exists makes the namespace settle on its
        own: the first run invents a key, later runs are told it is there and
        reuse it. That is a better fix than a fixed vocabulary, which would have
        to guess in advance every fact anyone might want to keep.

        **Split rather than merged, and that split was learned the hard way.**
        Offered one flat list, four live runs stopped inventing keys and started
        *rotating* between the synonyms already in it -- which is bounded drift
        instead of unbounded, and still not one row per fact. The list contained
        synonyms because it included the extractor's own unreviewed proposals, so
        it was being handed its previous guesses as though they were vocabulary
        and its noise fed back into itself.

        An active key is one a person chose. That is the closest thing this
        system has to a canonical name for a fact, and it is the set worth
        preferring. Proposals are still offered, because leaving them out brings
        back the cross-run invention this exists to prevent -- a session whose
        suggestions are all unreviewed would otherwise offer nothing at all.

        Not on ``SessionRepository``, for the reason ``count_proposals`` gives.
        """
        row = await self._require(session_id)

        session_keys = (
            await self._db.exec(
                select(ChatMemoryEntry.key).where(ChatMemoryEntry.session_id == session_id)
            )
        ).all()
        user_keys = (
            await self._db.exec(
                select(ChatUserMemoryEntry.key).where(ChatUserMemoryEntry.user_id == row.user_id)
            )
        ).all()
        proposed = (
            await self._db.exec(
                select(ChatMemoryProposal.key).where(ChatMemoryProposal.session_id == session_id)
            )
        ).all()

        active = frozenset(session_keys) | frozenset(user_keys)
        # A key that is both active and proposed counts as active: the standing
        # of a name is the strongest claim anything makes about it, and listing
        # it twice would suggest the two are competing when one is settled.
        return KnownKeys(active=active, proposed=frozenset(proposed) - active)

    async def count_proposals(self, session_id: str) -> int:
        """How many suggestions are waiting for a decision.

        Deliberately not on ``SessionRepository``. The agent has no use for it —
        proposals reach no model, so nothing in a turn depends on how many there
        are — and the protocol is one a second host has to satisfy in full, so
        widening it for a convenience this host wants would charge everyone for
        it. A structural protocol lets an implementation carry extra methods.

        A count rather than ``get_state``, which is what the caller would
        otherwise reach for: that loads the entire transcript to answer a
        question about one small table, and it would do it on every turn.

        Raises nothing on an unknown session. Zero is the honest answer to "how
        many are waiting" for a session that holds none, and the callers that
        must distinguish absent from empty already do so through ``get_state``.
        """
        return (
            await self._db.exec(
                select(func.count())
                .select_from(ChatMemoryProposal)
                .where(ChatMemoryProposal.session_id == session_id)
            )
        ).one()

    async def remember(
        self,
        session_id: str,
        key: str,
        value: Any,
        reason: str,
        source: str = OWNER,
        scope: MemoryScope = SESSION_SCOPE,
    ) -> MemoryEntry:
        row = await self._require(session_id)
        return await self._memory.remember(
            session_id, row.user_id, key, value, reason, source, scope
        )

    async def forget(self, session_id: str, key: str, scope: MemoryScope = SESSION_SCOPE) -> None:
        row = await self._require(session_id)
        await self._memory.forget(session_id, row.user_id, key, scope)

    async def propose(
        self,
        session_id: str,
        key: str,
        value: Any,
        reason: str,
        source: str,
        prompt_version: str | None = None,
    ) -> None:
        """Write a suggestion where proposals live. Reaches no model.

        ``prompt_version`` is an optional extra this implementation accepts and
        the agent's ``SessionRepository`` does not declare -- the same latitude
        ``known_keys`` and ``count_proposals`` take.
        """
        await self._require(session_id)
        await self._memory.propose(session_id, key, value, reason, source, prompt_version)

    async def activate(
        self, session_id: str, source: str, key: str, scope: MemoryScope = SESSION_SCOPE
    ) -> MemoryEntry:
        """Move a proposal into active memory.

        Raises:
            KeyError: No such proposal. Matches the in-memory store rather than
                silently creating a memory from nothing.
        """
        row = await self._require(session_id)
        return await self._memory.activate(session_id, row.user_id, source, key, scope)

    async def reject(self, session_id: str, source: str, key: str) -> None:
        """Discard a proposal. A no-op if it is not there, matching ``forget``."""
        await self._require(session_id)
        await self._memory.reject(session_id, source, key)

    async def _require(self, session_id: str, *, lock: bool = False) -> ChatSession:
        """Load the session row or raise the agent's own error type.

        Raising ``UnknownSessionError`` rather than returning ``None`` keeps this
        implementation indistinguishable from the in-memory one at the point
        callers handle it — a runtime that caught one and not the other would
        behave differently depending on which store it was given.

        Args:
            lock: Take a row lock (``SELECT ... FOR UPDATE``) held until the
                transaction ends. Only :meth:`commit` needs it, and only because
                it computes the next ``seq`` from what it reads. Reads do not
                take it: a lock on ``get_state`` would serialize every request
                for a session behind every other, to protect nothing.
        """
        if lock:
            row = (
                await self._db.exec(
                    select(ChatSession)
                    .where(ChatSession.session_id == session_id)
                    .with_for_update()
                )
            ).one_or_none()
        else:
            row = await self._db.get(ChatSession, session_id)
        if row is None:
            raise UnknownSessionError(session_id)
        return row
