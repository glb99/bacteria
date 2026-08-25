"""The seam exists, and the repository actually goes through it.

A refactor that only moves code is proved by the suite that already passes — and
that proof says nothing about the thing the move was *for*. What matters here is
that memory can come from somewhere else, so this substitutes a store and checks
the repository asks it rather than the tables.

Pure — no database. The point is delegation, and a database would only prove the
one implementation this deliberately does not use.
"""

from typing import Any, Optional

import pytest

from bacteria.agent.session.store import OWNER, SESSION_SCOPE, MemoryEntry, MemoryScope
from bacteria.app.chat.memory import MemoryView
from bacteria.app.chat.repository import SqlSessionRepository


class RecordingStore:
    """A `MemoryStore` that answers from nothing and remembers being asked."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...]]] = []
        self.view = MemoryView(memory={"tone": MemoryEntry(value="concise", reason="said so")})

    async def entries(self, session_id: str, user_id: str) -> MemoryView:
        self.calls.append(("entries", (session_id, user_id)))
        return self.view

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
        self.calls.append(("remember", (session_id, user_id, key, value, scope)))
        return MemoryEntry(value=value, reason=reason, source=source)

    async def forget(
        self, session_id: str, user_id: str, key: str, scope: MemoryScope = SESSION_SCOPE
    ) -> None:
        self.calls.append(("forget", (session_id, user_id, key, scope)))

    async def propose(
        self,
        session_id: str,
        key: str,
        value: Any,
        reason: str,
        source: str,
        prompt_version: Optional[str] = None,
    ) -> None:
        self.calls.append(("propose", (session_id, key, source)))

    async def activate(
        self,
        session_id: str,
        user_id: str,
        source: str,
        key: str,
        scope: MemoryScope = SESSION_SCOPE,
    ) -> MemoryEntry:
        self.calls.append(("activate", (session_id, user_id, source, key, scope)))
        return MemoryEntry(value="x", reason="y")

    async def reject(self, session_id: str, source: str, key: str) -> None:
        self.calls.append(("reject", (session_id, source, key)))


@pytest.fixture(name="store")
def _store():
    return RecordingStore()


async def test_state_reads_memory_through_the_port(store, engine):
    """`get_state` must not reach the tables directly, or the seam is decoration."""
    from sqlmodel.ext.asyncio.session import AsyncSession

    async with AsyncSession(engine) as db:
        repo = SqlSessionRepository(db)
        session = await repo.create_session("port-reader")

        through = SqlSessionRepository(db, memory=store)
        state = await through.get_state(session.session_id)

    assert state.memory["tone"].value == "concise", "the substitute answered"
    assert store.calls == [("entries", (session.session_id, "port-reader"))]


async def test_every_memory_method_delegates(store, engine):
    """One left behind would keep two sources of truth and nothing would say so."""
    from sqlmodel.ext.asyncio.session import AsyncSession

    async with AsyncSession(engine) as db:
        session = await SqlSessionRepository(db).create_session("port-writer")
        repo = SqlSessionRepository(db, memory=store)
        sid = session.session_id

        await repo.remember(sid, "tone", "concise", "said so")
        await repo.forget(sid, "tone")
        await repo.propose(sid, "tone", "terse", "guessed", source="extractor")
        await repo.activate(sid, "extractor", "tone")
        await repo.reject(sid, "extractor", "tone")

    assert [name for name, _ in store.calls] == [
        "remember",
        "forget",
        "propose",
        "activate",
        "reject",
    ]


async def test_the_owner_is_told_rather_than_looked_up(store, engine):
    """The caller has already checked ownership; a store resolving it again would
    be a second place for that check to be wrong."""
    from sqlmodel.ext.asyncio.session import AsyncSession

    async with AsyncSession(engine) as db:
        session = await SqlSessionRepository(db).create_session("owner-told")
        repo = SqlSessionRepository(db, memory=store)
        await repo.remember(session.session_id, "tone", "concise", "said so")

    assert store.calls[0][1][1] == "owner-told"


async def test_an_unknown_session_never_reaches_the_store(engine):
    """The session check stays in the repository, because it is also the
    ownership check -- and a store asked about a session nobody owns would be
    the second place that decision is made."""
    from sqlmodel.ext.asyncio.session import AsyncSession

    from bacteria.agent.session.store import UnknownSessionError

    store = RecordingStore()
    async with AsyncSession(engine) as db:
        repo = SqlSessionRepository(db, memory=store)
        with pytest.raises(UnknownSessionError):
            await repo.remember("no-such-session", "tone", "concise", "said so")

    assert store.calls == []
