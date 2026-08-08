"""The contract a session store must satisfy, and the only one callers use.

This is the seam the persistence gap in :mod:`bacteria.session.store` promised:
a durable store is *a second implementation of these five methods*, not a change
to any caller. :class:`~bacteria.runtime.runtime.Runtime` is written against this
protocol and never against the in-memory class, so an application can supply a
Postgres- or SQLite-backed store without this package learning what a database
is. The dependency runs outward — bacteria declares the shape, whoever hosts it
implements the shape — which is what keeps the agent vendorable into a project
whose persistence looks nothing like the one imagined here.

**Five methods, and deliberately not CRUD.** There is no ``update``. A generic
create/read/update/delete interface would fit this class in shape and destroy
the property it exists to have: exactly one deterministic, non-model code path
writes turn state, and that path is ``commit``. An ``update`` method is a second
write path by definition. ``remember`` and ``forget`` are separate again,
because a memory is a decision with its own lifecycle rather than a byproduct of
a turn — routing it through ``commit`` would make "keep this permanently" and
"stash this for the current turn" the same call.

**What an implementation must guarantee**, beyond having the methods — none of
which a type checker can verify, all of which callers depend on:

- ``get_state`` returns a *detached copy*. A caller that mutates what it read
  must change nothing. This is what makes "only this layer writes" structural
  rather than a rule everyone remembers; an implementation returning a live
  reference satisfies the protocol and breaks the system.
- ``commit`` appends transcript items and merges working state. It never
  replaces either wholesale, and the two never touch each other.
- ``remember`` overwrites by key; ``forget`` on an absent key is a no-op.
- An unknown ``session_id`` raises
  :class:`~bacteria.session.store.UnknownSessionError` rather than creating a
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

from bacteria.session.store import Session, SessionState, TranscriptItem


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
    ) -> SessionState:
        """Apply a proposed change. The only write path for turn state."""
        ...

    async def remember(
        self, session_id: str, key: str, value: Any, reason: str
    ) -> SessionState:
        """Record a fact worth re-surfacing later. The only write path for memory."""
        ...

    async def forget(self, session_id: str, key: str) -> SessionState:
        """Remove a memory."""
        ...
