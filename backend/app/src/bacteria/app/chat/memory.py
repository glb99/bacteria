"""Where a keyed memory comes from, behind an interface so it can come from elsewhere.

Two stores hold facts about a person: these tables, and the assertion graph. The
graph is the richer one and nothing reads it, because until now there was nowhere
to plug it in — the memory methods lived inside a 760-line repository alongside
sessions, the transcript and an extraction watermark, none of which are memory
and none of which the graph holds.

**The port is narrower than ``SessionRepository`` deliberately.** ADR 0010 says
why at length: a graph-backed *repository* would delegate most of its surface to
this one and override five methods, which is one implementation with a swappable
part described as two. Worse, the two objects would then differ in places
irrelevant to the question, and a comparison whose sides differ in irrelevant
ways is an anecdote.

So what varies is here and nothing else is: sessions, transcript, ``commit`` and
``extraction_progress`` are identical under either backing and stay where they
are.

**Which collection a row is in decides whether it reaches a model**, and this
interface keeps that property for the table implementation: ``memory`` comes from
one table, ``proposals`` from another, and there is no status column to forget to
filter on. A graph-backed implementation cannot have that guarantee — one log
holds both — and ADR 0010 §5 records what replaces it and why it is weaker.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional, Protocol

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from bacteria.agent.session.store import (
    OWNER,
    SESSION_SCOPE,
    USER_SCOPE,
    MemoryEntry,
    MemoryScope,
)
from bacteria.app.chat.models import (
    ChatMemoryEntry,
    ChatMemoryProposal,
    ChatUserMemoryEntry,
)


@dataclass(frozen=True)
class MemoryView:
    """The three collections a session state carries, read together.

    Together rather than one call each, because ``get_state`` needs all three and
    two round trips would let them disagree — a proposal activated between the
    reads would appear in neither, or in both.
    """

    memory: dict[str, MemoryEntry] = field(default_factory=dict)
    user_memory: dict[str, MemoryEntry] = field(default_factory=dict)
    proposals: dict[tuple[str, str], MemoryEntry] = field(default_factory=dict)


class MemoryStore(Protocol):
    """Where keyed memory lives, for one implementation to be swapped for another.

    ``user_id`` is a parameter rather than something an implementation looks up.
    The caller has already loaded the session and checked ownership, and a store
    that resolved it again would be a second place for that check to be wrong.
    """

    async def entries(self, session_id: str, user_id: str) -> MemoryView: ...

    async def remember(
        self,
        session_id: str,
        user_id: str,
        key: str,
        value: Any,
        reason: str,
        source: str = OWNER,
        scope: MemoryScope = SESSION_SCOPE,
    ) -> MemoryEntry: ...

    async def forget(
        self, session_id: str, user_id: str, key: str, scope: MemoryScope = SESSION_SCOPE
    ) -> None: ...

    async def propose(
        self,
        session_id: str,
        key: str,
        value: Any,
        reason: str,
        source: str,
        prompt_version: Optional[str] = None,
    ) -> None: ...

    async def activate(
        self,
        session_id: str,
        user_id: str,
        source: str,
        key: str,
        scope: MemoryScope = SESSION_SCOPE,
    ) -> MemoryEntry: ...

    async def reject(self, session_id: str, source: str, key: str) -> None: ...


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _entry(row: Any) -> MemoryEntry:
    return MemoryEntry(
        value=row.value["value"],
        reason=row.reason,
        source=row.source,
        created_at=_as_utc(row.created_at),
    )


class TableMemoryStore:
    """The implementation that has always been here, moved rather than rewritten.

    Every method below is the body that was in ``SqlSessionRepository``, with the
    session lookup taken out: the caller does that, because it also decides
    whether the caller may have the session at all.
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def entries(self, session_id: str, user_id: str) -> MemoryView:
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
        user_memories = (
            await self._db.exec(
                select(ChatUserMemoryEntry).where(ChatUserMemoryEntry.user_id == user_id)
            )
        ).all()

        return MemoryView(
            memory={row.key: _entry(row) for row in memories},
            user_memory={row.key: _entry(row) for row in user_memories},
            # Keyed by (source, key), matching the table's own primary key.
            # Which collection a row lands in is decided by which table it came
            # from -- there is no status column to filter on and therefore none
            # to forget to filter on.
            proposals={(row.source, row.key): _entry(row) for row in proposals},
        )

    async def remember(
        self,
        session_id: str,
        user_id: str,
        key: str,
        value: Any,
        reason: str,
        source: str = OWNER,
        scope: MemoryScope = SESSION_SCOPE,
    ) -> MemoryEntry:

        if scope == USER_SCOPE:
            entry = await self._write_user_memory(
                user_id, key=key, value=value, reason=reason, source=source
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

    async def forget(
        self, session_id: str, user_id: str, key: str, scope: MemoryScope = SESSION_SCOPE
    ) -> None:

        if scope == USER_SCOPE:
            existing = await self._db.get(ChatUserMemoryEntry, (user_id, key))
        else:
            existing = await self._db.get(ChatMemoryEntry, (session_id, key))
        if existing is not None:
            await self._db.delete(existing)
            await self._db.commit()
        # Absent key is a no-op: the caller wanted it gone, and it is.

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
        self,
        session_id: str,
        user_id: str,
        source: str,
        key: str,
        scope: MemoryScope = SESSION_SCOPE,
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

        proposal = await self._db.get(ChatMemoryProposal, (session_id, source, key))
        if proposal is None:
            raise KeyError((source, key))

        if scope == USER_SCOPE:
            entry = await self._write_user_memory(
                user_id,
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

        existing = await self._db.get(ChatMemoryProposal, (session_id, source, key))
        if existing is not None:
            await self._db.delete(existing)
            await self._db.commit()
