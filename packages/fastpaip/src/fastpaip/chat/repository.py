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

Not built:
    Concurrency control. ``commit`` reads the current maximum ``seq`` and writes
    the next one, and two concurrent commits to the same session can therefore
    both read the same maximum. The agent's store documents the same gap and the
    same fix — a version column checked before applying — and it becomes real
    here first, since two HTTP requests for one session are ordinary where two
    CLI turns were not.

    Pagination. ``get_state`` loads the entire transcript, which is bounded only
    by how long a conversation runs. The agent's context assembly windows what
    it sends to a model, so this is a memory and latency cost rather than a
    correctness one — until a conversation is long enough for it not to be.
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from bacteria.session.store import (
    MemoryEntry,
    Session,
    SessionState,
    TranscriptItem,
    UnknownSessionError,
)
from sqlalchemy import func
from sqlmodel import Session as DbSession
from sqlmodel import select

from fastpaip.chat.models import ChatMemoryEntry, ChatSession, ChatTranscriptItem


def _as_utc(value: datetime) -> datetime:
    """Reattach UTC to a datetime a backend handed back without one.

    SQLite stores no timezone, so a value written as aware comes back naive and
    would then be compared as local time. Assuming UTC is correct because that
    is the only thing ever written.
    """
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


class SqlSessionRepository:
    """Stores agent sessions in a relational database.

    Satisfies :class:`bacteria.session.protocol.SessionRepository` structurally.

    The methods are ``async`` because the protocol is, while the SQLModel calls
    inside them are synchronous — so each one blocks its thread for the duration
    of a query. That is a real limitation and not a hidden one: it is fine
    against SQLite and under light load, and it is the first thing to change if
    this ever sits in front of a busy Postgres. Doing it properly means an async
    engine and an async session, which is a larger change than this feature
    needed to prove the seam works.

    Args:
        session: An open database session. Injected rather than created here,
            so that transaction scope belongs to whoever knows what a unit of
            work is — for a request, that is the dependency that opened it.
    """

    def __init__(self, session: DbSession) -> None:
        self._db = session

    async def create_session(self, user_id: str) -> Session:
        row = ChatSession(session_id=str(uuid.uuid4()), user_id=user_id)
        self._db.add(row)
        self._db.commit()
        self._db.refresh(row)
        return Session(
            session_id=row.session_id,
            user_id=row.user_id,
            created_at=_as_utc(row.created_at),
        )

    async def get_state(self, session_id: str) -> SessionState:
        row = self._require(session_id)

        items = self._db.exec(
            select(ChatTranscriptItem)
            .where(ChatTranscriptItem.session_id == session_id)
            .order_by(ChatTranscriptItem.seq)
        ).all()
        memories = self._db.exec(
            select(ChatMemoryEntry).where(ChatMemoryEntry.session_id == session_id)
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
                    kind=item.kind,
                    payload=dict(item.payload),
                    timestamp=_as_utc(item.timestamp),
                )
                for item in items
            ],
            working_state=dict(row.working_state),
            memory={
                entry.key: MemoryEntry(
                    value=entry.value["value"],
                    reason=entry.reason,
                    created_at=_as_utc(entry.created_at),
                )
                for entry in memories
            },
        )

    async def commit(
        self,
        session_id: str,
        new_transcript_items: Optional[list[TranscriptItem]] = None,
        working_state_updates: Optional[dict[str, Any]] = None,
    ) -> SessionState:
        row = self._require(session_id)

        next_seq = (
            self._db.exec(
                select(func.coalesce(func.max(ChatTranscriptItem.seq), -1)).where(
                    ChatTranscriptItem.session_id == session_id
                )
            ).one()
            + 1
        )
        for offset, item in enumerate(new_transcript_items or []):
            self._db.add(
                ChatTranscriptItem(
                    session_id=session_id,
                    seq=next_seq + offset,
                    kind=item.kind,
                    payload=item.payload,
                    timestamp=item.timestamp,
                )
            )

        if working_state_updates:
            # Rebound rather than mutated in place: SQLAlchemy does not track
            # mutations inside a plain JSON column, so `row.working_state[k] = v`
            # updates the object in memory and writes nothing.
            row.working_state = {**row.working_state, **working_state_updates}
            self._db.add(row)

        self._db.commit()
        return await self.get_state(session_id)

    async def remember(
        self, session_id: str, key: str, value: Any, reason: str
    ) -> SessionState:
        self._require(session_id)

        existing = self._db.get(ChatMemoryEntry, (session_id, key))
        if existing is not None:
            # Overwrite by key: updating a memory is a write, not an append.
            existing.value = {"value": value}
            existing.reason = reason
            self._db.add(existing)
        else:
            self._db.add(
                ChatMemoryEntry(
                    session_id=session_id, key=key, value={"value": value}, reason=reason
                )
            )

        self._db.commit()
        return await self.get_state(session_id)

    async def forget(self, session_id: str, key: str) -> SessionState:
        self._require(session_id)

        existing = self._db.get(ChatMemoryEntry, (session_id, key))
        if existing is not None:
            self._db.delete(existing)
            self._db.commit()
        # Absent key is a no-op: the caller wanted it gone, and it is.
        return await self.get_state(session_id)

    def _require(self, session_id: str) -> ChatSession:
        """Load the session row or raise the agent's own error type.

        Raising ``UnknownSessionError`` rather than returning ``None`` keeps this
        implementation indistinguishable from the in-memory one at the point
        callers handle it — a runtime that caught one and not the other would
        behave differently depending on which store it was given.
        """
        row = self._db.get(ChatSession, session_id)
        if row is None:
            raise UnknownSessionError(session_id)
        return row
