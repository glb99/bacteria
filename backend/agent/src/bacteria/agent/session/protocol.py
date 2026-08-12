"""The contract a session store must satisfy, and the only one callers use.

This is the seam the persistence gap in :mod:`bacteria.agent.session.store` promised:
a durable store is *a second implementation of these five methods*, not a change
to any caller. :class:`~bacteria.agent.runtime.runtime.Runtime` is written against this
protocol and never against the in-memory class, so an application can supply a
Postgres- or SQLite-backed store without this package learning what a database
is. The dependency runs outward — bacteria declares the shape, whoever hosts it
implements the shape — which is what keeps the agent vendorable into a project
whose persistence looks nothing like the one imagined here.

**Eight methods, and deliberately not CRUD.** There is no ``update``. A generic
create/read/update/delete interface would fit this class in shape and destroy
the property it exists to have: exactly one deterministic, non-model code path
writes turn state, and that path is ``commit``. An ``update`` method is a second
write path by definition.

The memory methods are separate from ``commit`` and from each other because a
memory is a decision with its own lifecycle rather than a byproduct of a turn.
Routing it through ``commit`` would make "keep this permanently" and "stash this
for the current turn" the same call, and collapsing the four into one would
erase the distinction ADR 0017 exists to draw:

- ``remember`` / ``forget`` — the owner's writes, active immediately.
- ``propose`` / ``activate`` / ``reject`` — everything else. A proposal reaches
  no model until a human activates it, so a tool the model called cannot write
  its own future instructions.

Five of these are what a *runtime* needs; ``activate`` and ``reject`` are what a
review surface needs. They are declared together because they are one lifecycle
and a store that implemented half of it would be a store where proposals could
be created and never resolved.

**What an implementation must guarantee**, beyond having the methods — none of
which a type checker can verify, all of which callers depend on:

- ``get_state`` returns a *detached copy*. A caller that mutates what it read
  must change nothing. This is what makes "only this layer writes" structural
  rather than a rule everyone remembers; an implementation returning a live
  reference satisfies the protocol and breaks the system.
- ``commit`` appends transcript items and merges working state. It never
  replaces either wholesale, and the two never touch each other.
- ``remember`` overwrites by key; ``forget`` on an absent key is a no-op.
- ``user``-scoped memory belongs to the session's *owner*, not to the session.
  Two sessions of one person see the same entries, and one person's are never
  visible to another. An implementation storing it per session satisfies every
  signature here and silently reimplements session scope.
- An unknown ``session_id`` raises
  :class:`~bacteria.agent.session.store.UnknownSessionError` rather than creating a
  session, because an id that does not resolve usually means a caller lost one.

A conformance suite for the guarantees above exists, but *in the host* — the
application implementing this protocol runs the same behaviours against both its
own store and the in-memory one. That is the right place for it while there is
one host; the guarantees are this package's, though, so a second host would have
to write its own rather than inherit one.

Not built:
    A conformance suite shipped from here — a set of tests parameterized over an
    implementation, exported so any host can run them against its own store
    without rewriting them. What exists today verifies this protocol only as
    long as that one host keeps doing it.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from bacteria.agent.session.store import (
    MemoryEntry,
    MemoryScope,
    Session,
    SessionState,
    TranscriptItem,
)


@runtime_checkable
class SessionRepository(Protocol):
    """What the runtime requires of a session store — the whole of it.

    Structural: an implementation inherits nothing and registers nothing.
    ``runtime_checkable`` is set so conformance can be asserted in a test, with
    the same caveat as elsewhere in this package — it verifies the methods
    exist, not that they behave, and the behavioral guarantees above are the
    ones that matter.
    """

    async def create_session(self, user_id: str) -> Session:
        """Open a new, empty session for ``user_id``."""
        ...

    async def get_state(self, session_id: str) -> SessionState:
        """Read a session's state as a detached copy."""
        ...

    async def commit(
        self,
        session_id: str,
        new_transcript_items: list[TranscriptItem] | None = None,
        working_state_updates: dict[str, Any] | None = None,
    ) -> None:
        """Apply a proposed change. The only write path for turn state."""
        ...

    async def remember(
        self,
        session_id: str,
        key: str,
        value: Any,
        reason: str,
        source: str = "owner",
        scope: MemoryScope = "session",
    ) -> MemoryEntry:
        """Write an active memory directly. For the session's owner only.

        Returns the entry written, which is what a caller wants and what an
        implementation already holds — see ADR 0023 for why this is not a
        ``SessionState``.
        """
        ...

    async def forget(self, session_id: str, key: str, scope: MemoryScope = "session") -> None:
        """Remove an active memory."""
        ...

    async def propose(
        self, session_id: str, key: str, value: Any, reason: str, source: str
    ) -> None:
        """Suggest a memory. Reaches no model until activated.

        Deliberately has no ``scope``: whoever proposes does not choose how far
        the result reaches. See :meth:`activate`.
        """
        ...

    async def activate(
        self, session_id: str, source: str, key: str, scope: MemoryScope = "session"
    ) -> MemoryEntry:
        """Promote a proposal into active memory, at a scope the human picks."""
        ...

    async def reject(self, session_id: str, source: str, key: str) -> None:
        """Discard a proposal."""
        ...
