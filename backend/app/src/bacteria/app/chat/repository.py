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
    USER_SCOPE,
    MemoryEntry,
    MemoryScope,
    Session,
    SessionState,
    TranscriptItem,
    TranscriptItemKind,
    UnknownSessionError,
)
from bacteria.app.chat.models import (
    ChatMemoryEntry,
    ChatMemoryExtraction,
    ChatMemoryProposal,
    ChatSession,
    ChatTranscriptItem,
    ChatUserMemoryEntry,
)


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

        if scope == USER_SCOPE:
            entry = await self._write_user_memory(
                row.user_id, key=key, value=value, reason=reason, source=source
            )
            await self._db.commit()
            return entry

        # The timestamp is taken once and used for both the row and the returned
        # entry, rather than left to the column default on the insert path. The
        # caller is handed the same value that was stored; deriving it twice is
        # how the two paths would come to differ by microseconds.
        now = datetime.now(timezone.utc)
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
            existing.created_at = now
            # Cleared, because this write did not come from a prompt. Leaving the
            # previous value would attribute an owner's sentence to the extractor
            # wording that proposed the fact it replaced.
            existing.prompt_version = None
            self._db.add(existing)
        else:
            self._db.add(
                ChatMemoryEntry(
                    session_id=session_id,
                    key=key,
                    value={"value": value},
                    reason=reason,
                    source=source,
                    created_at=now,
                )
            )

        await self._db.commit()
        return MemoryEntry(value=value, reason=reason, source=source, created_at=now)

    async def forget(self, session_id: str, key: str, scope: MemoryScope = SESSION_SCOPE) -> None:
        row = await self._require(session_id)

        if scope == USER_SCOPE:
            existing = await self._db.get(ChatUserMemoryEntry, (row.user_id, key))
        else:
            existing = await self._db.get(ChatMemoryEntry, (session_id, key))
        if existing is not None:
            await self._db.delete(existing)
            await self._db.commit()
        # Absent key is a no-op: the caller wanted it gone, and it is.

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

    async def propose(
        self,
        session_id: str,
        key: str,
        value: Any,
        reason: str,
        source: str,
        prompt_version: str | None = None,
    ) -> None:
        """Write a suggestion into the proposals table. Reaches no model.

        ``prompt_version`` is an optional extra this implementation accepts and
        the agent's ``SessionRepository`` does not declare — the same latitude
        ``known_keys`` and ``count_proposals`` take. A proposer that has a
        version supplies it; one that does not is unaffected, and a second host
        implementing the protocol owes nothing.
        """
        await self._require(session_id)

        existing = await self._db.get(ChatMemoryProposal, (session_id, source, key))
        if existing is not None:
            # Replaces this source's own earlier suggestion for the key, which
            # is what makes a retried job idempotent rather than accumulative.
            # A *different* source proposing the same key is a different row.
            existing.value = {"value": value}
            existing.reason = reason
            existing.created_at = datetime.now(timezone.utc)
            # Overwritten with the caller's value including when that value is
            # None, because this row is now the newer proposer's. Keeping a
            # previous version would attribute a re-proposal to wording that did
            # not produce it -- which is the one thing this column exists to
            # prevent.
            existing.prompt_version = prompt_version
            self._db.add(existing)
        else:
            self._db.add(
                ChatMemoryProposal(
                    session_id=session_id,
                    source=source,
                    key=key,
                    value={"value": value},
                    reason=reason,
                    prompt_version=prompt_version,
                )
            )

        await self._db.commit()

    async def _write_user_memory(
        self,
        user_id: str,
        key: str,
        value: Any,
        reason: str,
        source: str,
        prompt_version: str | None = None,
    ) -> MemoryEntry:
        """Upsert one user-scoped entry. Does not commit.

        Shared by ``remember`` and ``activate`` so the two cannot drift on
        overwrite semantics — which is exactly how the session-scoped versions
        drifted on ``created_at`` once already. Refreshing the timestamp is the
        behaviour the assembly bound needs: it shows the most recent entries, so
        a memory the owner just rewrote must not be at risk of ageing out.

        ``prompt_version`` travels with the value it describes and is therefore
        overwritten unconditionally, ``None`` included: an owner rewriting a fact
        an extractor proposed is not still that extractor's wording, and keeping
        the old version would attribute a human's sentence to a prompt.
        """
        now = datetime.now(timezone.utc)
        existing = await self._db.get(ChatUserMemoryEntry, (user_id, key))
        if existing is not None:
            existing.value = {"value": value}
            existing.reason = reason
            existing.source = source
            existing.created_at = now
            existing.prompt_version = prompt_version
            self._db.add(existing)
        else:
            self._db.add(
                ChatUserMemoryEntry(
                    user_id=user_id,
                    key=key,
                    value={"value": value},
                    reason=reason,
                    source=source,
                    created_at=now,
                    prompt_version=prompt_version,
                )
            )
        return MemoryEntry(value=value, reason=reason, source=source, created_at=now)

    async def activate(
        self, session_id: str, source: str, key: str, scope: MemoryScope = SESSION_SCOPE
    ) -> MemoryEntry:
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
            entry = await self._write_user_memory(
                row.user_id,
                key=key,
                value=proposal.value["value"],
                reason=proposal.reason,
                source=proposal.source,
                prompt_version=proposal.prompt_version,
            )
            await self._db.delete(proposal)
            await self._db.commit()
            return entry

        activated = MemoryEntry(
            value=proposal.value["value"],
            reason=proposal.reason,
            source=proposal.source,
            created_at=datetime.now(timezone.utc),
        )
        existing = await self._db.get(ChatMemoryEntry, (session_id, key))
        if existing is not None:
            # Activation is where competing proposals collapse onto one key --
            # the reviewer chose this one, so it replaces whatever held it.
            existing.value = proposal.value
            existing.reason = proposal.reason
            existing.source = proposal.source
            existing.created_at = activated.created_at
            # Carried across activation, which is the whole reason this column is
            # on the shared base rather than on the proposal table: "which wording
            # produced the memories people actually accepted" is the question that
            # says whether changing a prompt helped, and discarding the version at
            # the moment of acceptance is precisely where it would be lost.
            existing.prompt_version = proposal.prompt_version
            self._db.add(existing)
        else:
            self._db.add(
                ChatMemoryEntry(
                    session_id=session_id,
                    key=key,
                    value=proposal.value,
                    reason=proposal.reason,
                    source=proposal.source,
                    created_at=activated.created_at,
                    prompt_version=proposal.prompt_version,
                )
            )
        await self._db.delete(proposal)

        await self._db.commit()
        return activated

    async def reject(self, session_id: str, source: str, key: str) -> None:
        """Discard a proposal. A no-op if it is not there, matching ``forget``."""
        await self._require(session_id)

        existing = await self._db.get(ChatMemoryProposal, (session_id, source, key))
        if existing is not None:
            await self._db.delete(existing)
            await self._db.commit()

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
