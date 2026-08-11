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
from datetime import datetime, timezone
from typing import Any, Optional, cast

from bacteria.session.store import (
    OWNER,
    SESSION_SCOPE,
    USER_SCOPE,
    MemoryEntry,
    MemoryScope,
    Session,
    SessionState,
    TranscriptItem,
    TranscriptItemKind,
    UnknownSessionError,
)
from sqlalchemy import func
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from fastpaip.chat.models import (
    ChatMemoryEntry,
    ChatMemoryProposal,
    ChatSession,
    ChatTranscriptItem,
    ChatUserMemoryEntry,
)


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


class SqlSessionRepository:
    """Stores agent sessions in a relational database.

    Satisfies :class:`bacteria.session.protocol.SessionRepository` structurally.

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

    def __init__(self, session: AsyncSession) -> None:
        self._db = session

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
        memories = (
            await self._db.exec(
                select(ChatMemoryEntry).where(ChatMemoryEntry.session_id == session_id)
            )
        ).all()
        proposals = (
            await self._db.exec(
                select(ChatMemoryProposal).where(ChatMemoryProposal.session_id == session_id)
            )
        ).all()
        # Selected by the owner of *this* session and by nothing else. This is
        # the only query in the application that reaches rows not keyed by
        # `session_id`, so it is the only one where a wrong predicate would show
        # one person another's memory rather than merely the wrong conversation.
        # `row.user_id` comes from the session already loaded above, which the
        # route has already checked the caller owns.
        user_memories = (
            await self._db.exec(
                select(ChatUserMemoryEntry).where(ChatUserMemoryEntry.user_id == row.user_id)
            )
        ).all()

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
            memory={
                entry.key: MemoryEntry(
                    value=entry.value["value"],
                    reason=entry.reason,
                    source=entry.source,
                    created_at=_as_utc(entry.created_at),
                )
                for entry in memories
            },
            user_memory={
                entry.key: MemoryEntry(
                    value=entry.value["value"],
                    reason=entry.reason,
                    source=entry.source,
                    created_at=_as_utc(entry.created_at),
                )
                for entry in user_memories
            },
            # Keyed by (source, key), matching the table's own primary key.
            # Which collection a row lands in is decided by which table it came
            # from -- there is no status column to filter on and therefore none
            # to forget to filter on.
            proposals={
                (entry.source, entry.key): MemoryEntry(
                    value=entry.value["value"],
                    reason=entry.reason,
                    source=entry.source,
                    created_at=_as_utc(entry.created_at),
                )
                for entry in proposals
            },
        )

    async def commit(
        self,
        session_id: str,
        new_transcript_items: Optional[list[TranscriptItem]] = None,
        working_state_updates: Optional[dict[str, Any]] = None,
    ) -> SessionState:
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
        return await self.get_state(session_id)

    async def remember(
        self,
        session_id: str,
        key: str,
        value: Any,
        reason: str,
        source: str = OWNER,
        scope: MemoryScope = SESSION_SCOPE,
    ) -> SessionState:
        row = await self._require(session_id)

        if scope == USER_SCOPE:
            await self._write_user_memory(
                row.user_id, key=key, value=value, reason=reason, source=source
            )
            await self._db.commit()
            return await self.get_state(session_id)

        existing = await self._db.get(ChatMemoryEntry, (session_id, key))
        if existing is not None:
            existing.source = source
            # Overwrite by key: updating a memory is a write, not an append.
            existing.value = {"value": value}
            existing.reason = reason
            # `created_at` is refreshed, not preserved, and the two are not
            # interchangeable. The agent's in-memory store builds a whole new
            # MemoryEntry here, so its timestamp moves; leaving this one alone
            # made the two implementations disagree about the same call.
            #
            # Refreshing is also the behaviour the bound needs. Assembly shows
            # the model the most recent entries by this field, so a preserved
            # timestamp would let a memory the owner just rewrote age out and
            # stay invisible -- the one outcome nobody could explain.
            existing.created_at = datetime.now(timezone.utc)
            self._db.add(existing)
        else:
            self._db.add(
                ChatMemoryEntry(
                    session_id=session_id,
                    key=key,
                    value={"value": value},
                    reason=reason,
                    source=source,
                )
            )

        await self._db.commit()
        return await self.get_state(session_id)

    async def forget(
        self, session_id: str, key: str, scope: MemoryScope = SESSION_SCOPE
    ) -> SessionState:
        row = await self._require(session_id)

        if scope == USER_SCOPE:
            existing = await self._db.get(ChatUserMemoryEntry, (row.user_id, key))
        else:
            existing = await self._db.get(ChatMemoryEntry, (session_id, key))
        if existing is not None:
            await self._db.delete(existing)
            await self._db.commit()
        # Absent key is a no-op: the caller wanted it gone, and it is.
        return await self.get_state(session_id)

    async def propose(
        self, session_id: str, key: str, value: Any, reason: str, source: str
    ) -> SessionState:
        """Write a suggestion into the proposals table. Reaches no model."""
        await self._require(session_id)

        existing = await self._db.get(ChatMemoryProposal, (session_id, source, key))
        if existing is not None:
            # Replaces this source's own earlier suggestion for the key, which
            # is what makes a retried job idempotent rather than accumulative.
            # A *different* source proposing the same key is a different row.
            existing.value = {"value": value}
            existing.reason = reason
            existing.created_at = datetime.now(timezone.utc)
            self._db.add(existing)
        else:
            self._db.add(
                ChatMemoryProposal(
                    session_id=session_id,
                    source=source,
                    key=key,
                    value={"value": value},
                    reason=reason,
                )
            )

        await self._db.commit()
        return await self.get_state(session_id)

    async def _write_user_memory(
        self, user_id: str, key: str, value: Any, reason: str, source: str
    ) -> None:
        """Upsert one user-scoped entry. Does not commit.

        Shared by ``remember`` and ``activate`` so the two cannot drift on
        overwrite semantics — which is exactly how the session-scoped versions
        drifted on ``created_at`` once already. Refreshing the timestamp is the
        behaviour the assembly bound needs: it shows the most recent entries, so
        a memory the owner just rewrote must not be at risk of ageing out.
        """
        existing = await self._db.get(ChatUserMemoryEntry, (user_id, key))
        if existing is not None:
            existing.value = {"value": value}
            existing.reason = reason
            existing.source = source
            existing.created_at = datetime.now(timezone.utc)
            self._db.add(existing)
        else:
            self._db.add(
                ChatUserMemoryEntry(
                    user_id=user_id,
                    key=key,
                    value={"value": value},
                    reason=reason,
                    source=source,
                )
            )

    async def activate(
        self, session_id: str, source: str, key: str, scope: MemoryScope = SESSION_SCOPE
    ) -> SessionState:
        """Move a proposal into active memory, in one transaction.

        Both writes commit together or neither does. A partial application here
        is the one outcome with no honest reading: a proposal deleted without
        the memory appearing loses a suggestion nobody can recover, and a memory
        written without the proposal cleared leaves a reviewer approving the
        same thing forever.

        Raises:
            KeyError: No such proposal. Matches the in-memory store rather than
                silently creating a memory from nothing, which would let a stale
                review page conjure a fact nobody just read.
        """
        row = await self._require(session_id)

        proposal = await self._db.get(ChatMemoryProposal, (session_id, source, key))
        if proposal is None:
            raise KeyError((source, key))

        if scope == USER_SCOPE:
            await self._write_user_memory(
                row.user_id,
                key=key,
                value=proposal.value["value"],
                reason=proposal.reason,
                source=proposal.source,
            )
            await self._db.delete(proposal)
            await self._db.commit()
            return await self.get_state(session_id)

        existing = await self._db.get(ChatMemoryEntry, (session_id, key))
        if existing is not None:
            # Activation is where competing proposals collapse onto one key --
            # the reviewer chose this one, so it replaces whatever held it.
            existing.value = proposal.value
            existing.reason = proposal.reason
            existing.source = proposal.source
            existing.created_at = datetime.now(timezone.utc)
            self._db.add(existing)
        else:
            self._db.add(
                ChatMemoryEntry(
                    session_id=session_id,
                    key=key,
                    value=proposal.value,
                    reason=proposal.reason,
                    source=proposal.source,
                )
            )
        await self._db.delete(proposal)

        await self._db.commit()
        return await self.get_state(session_id)

    async def reject(self, session_id: str, source: str, key: str) -> SessionState:
        """Discard a proposal. A no-op if it is not there, matching ``forget``."""
        await self._require(session_id)

        existing = await self._db.get(ChatMemoryProposal, (session_id, source, key))
        if existing is not None:
            await self._db.delete(existing)
            await self._db.commit()
        return await self.get_state(session_id)

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
