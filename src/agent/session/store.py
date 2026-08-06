"""The authoritative record of what a session is and what happened in it.

This module is the system's single source of truth. When the same fact exists
in more than one place — a runtime local, a returned copy, a future cache —
this is the copy that wins, and every other copy is derived.

State is deliberately split three ways rather than kept as one blob, because
the three have genuinely different lifecycles and merging them loses that:

- **transcript** — the durable record of what happened, append-only.
- **working_state** — scratch data for the current turn. Overwritable, and
  nothing should assume it survives.
- **memory** — facts deliberately preserved and deliberately re-surfaced later.
  A memory is a decision, not a byproduct, which is why it has its own write
  path and its own removal path instead of sharing ``commit``'s.

Invariant: nothing mutates authoritative state except :meth:`SessionStore.commit`,
:meth:`SessionStore.remember`, and :meth:`SessionStore.forget`. This is enforced
structurally rather than by convention — :meth:`SessionStore.get_state` returns a
deep copy, so a caller that mutates what it reads changes nothing. Without the
copy the invariant would hold only as long as every caller behaved, and the
class of bug it prevents (authoritative state quietly edited from outside the
module that owns it) is close to untraceable once it happens.

Everything a model or runtime produces reaches this store as a *proposal*: it is
passed to ``commit`` and becomes canonical only if ``commit`` applies it. The
model cannot see concurrency, ordering, or what the record looks like right now,
so it cannot hold commit authority — and neither can code holding a stale copy.
Nothing else may write.

Not built:
    Persistence. Sessions live in a process-local dict and vanish on exit, so
    there is no cross-session memory and no resume after a restart. The seam is
    already the right shape for it: ``SessionStore``'s four public methods are
    the complete set of operations a backing store would need to implement, so
    persistence means a second implementation of this class (SQLite, Postgres,
    Redis) plus a way to pick one, not a change to any caller. It drags in two
    things beyond the backend itself: serialization for :class:`TranscriptItem`
    and :class:`MemoryEntry`, and the concurrency control below.

    Concurrency control. ``commit`` assumes it is the only writer. With more
    than one, it would need a staleness check — a version or ETag on
    ``SessionState``, compared before applying and rejected on mismatch. That
    check belongs inside ``commit``, which is why it stays the only write path
    even though it is currently a thin one.

    Session routing. A caller must already know its ``session_id``; nothing
    here infers which session an incoming event belongs to. That decision needs
    a policy (resume, append, or fork) that only matters once runs can be
    interrupted or run concurrently.
"""

from __future__ import annotations

import copy
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

TranscriptItemKind = Literal["message", "tool_call", "run_error"]
"""The kinds of event a transcript can hold, and the payload each carries.

- ``message`` — ``{"role": "user" | "assistant", "text": str}``
- ``tool_call`` — ``{"name": str, "input": dict, "status": "executed" | "failed"}``
  plus ``"output"`` when executed, or ``"error"`` when failed. One item covers
  the whole attempt: a separate ``tool_result`` kind would let a call exist in
  the record with no visible outcome, which is the exact gap the item is here
  to close.
- ``run_error`` — ``{"error": str}``. A run that failed part-way, recorded so
  the failure leaves evidence rather than only an exception.

Kept as a closed ``Literal`` so that adding a kind is a typed change that
surfaces every reader needing to handle it.
"""


@dataclass(frozen=True)
class Session:
    """Identity of one conversation.

    ``session_id`` is generated here and never derived from ``user_id``: one
    user holds many sessions, and knowing who someone is says nothing about
    which of their conversations an event belongs to. Keeping the two separate
    also keeps identity from drifting into an implicit authorization check —
    "this session exists" must never come to mean "this action is allowed".
    """

    session_id: str
    user_id: str
    created_at: datetime


@dataclass(frozen=True)
class TranscriptItem:
    """One immutable entry in the durable record.

    Frozen because the transcript is append-only: correcting history means
    appending a correction, not editing what was already recorded.
    """

    kind: TranscriptItemKind
    payload: dict[str, Any]
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class MemoryEntry:
    """One deliberately preserved fact.

    ``reason`` is required, not optional. A memory with no recorded reason
    cannot be reviewed later — there is no way to judge whether it is still
    worth keeping, so it is kept forever by default. Requiring provenance at
    write time is what makes expiry a decision someone can actually make.
    """

    value: Any
    reason: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class SessionState:
    """Everything the store holds for one session.

    Mutable, unlike the items inside it, because ``commit`` mutates it in
    place. Callers never receive this object — only deep copies of it.
    """

    session: Session
    transcript: list[TranscriptItem] = field(default_factory=list)
    working_state: dict[str, Any] = field(default_factory=dict)
    memory: dict[str, MemoryEntry] = field(default_factory=dict)


class UnknownSessionError(KeyError):
    """The named session does not exist.

    Raised rather than creating the session implicitly: a session id that does
    not resolve usually means a caller lost track of one, and silently
    conjuring an empty session turns that into invisible data loss.
    """


class SessionStore:
    """In-memory implementation of the authoritative session store.

    Every public method that returns state returns a deep copy. That is the
    whole enforcement mechanism behind this module's central invariant, and the
    reason it is worth the copying cost at this scale.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, SessionState] = {}

    def create_session(self, user_id: str) -> Session:
        """Open a new, empty session for ``user_id``.

        Returns:
            The new session. Callers are responsible for holding onto
            ``session_id`` — nothing here can recover it from ``user_id``.
        """
        session = Session(
            session_id=str(uuid.uuid4()),
            user_id=user_id,
            created_at=datetime.now(timezone.utc),
        )
        self._sessions[session.session_id] = SessionState(session=session)
        return session

    def get_state(self, session_id: str) -> SessionState:
        """Read a session's state as a detached deep copy.

        Mutating the returned object has no effect on the store. This is not a
        defensive nicety — it is what makes "only ``commit`` writes" true by
        construction rather than by everyone remembering to behave.

        Raises:
            UnknownSessionError: No such session.
        """
        if session_id not in self._sessions:
            raise UnknownSessionError(session_id)
        return copy.deepcopy(self._sessions[session_id])

    def commit(
        self,
        session_id: str,
        new_transcript_items: list[TranscriptItem] | None = None,
        working_state_updates: dict[str, Any] | None = None,
    ) -> SessionState:
        """Apply a proposed change. The only write path for turn state.

        Takes the change as plain arguments rather than a separate proposal
        object. An earlier ``propose()`` step existed and was removed: it
        validated the session and built a dataclass, neither of which is the
        guarantee that matters. The guarantee is that exactly one deterministic,
        non-model code path writes, and one method provides it as fully as two.
        A future staleness or conflict check belongs *inside* this method.

        Transcript items append; working state merges key-by-key. The two never
        touch each other — that separation is the point of having both.

        Returns:
            A deep copy of the resulting state.

        Raises:
            UnknownSessionError: No such session.
        """
        if session_id not in self._sessions:
            raise UnknownSessionError(session_id)
        state = self._sessions[session_id]
        state.transcript.extend(new_transcript_items or [])
        state.working_state.update(working_state_updates or {})
        return copy.deepcopy(state)

    def remember(self, session_id: str, key: str, value: Any, reason: str) -> SessionState:
        """Record a fact worth re-surfacing later. The only write path for memory.

        Separate from :meth:`commit` on purpose. Routing memory through
        ``working_state_updates`` would make "remember this permanently" and
        "stash this for the current turn" the same call, and the difference
        between them is the entire reason memory exists as a distinct concern.

        Args:
            key: Overwrites any existing entry. Updating a memory is a write,
                not an append — the transcript is where history lives.
            reason: Why this is worth keeping. Required; see :class:`MemoryEntry`.

        Raises:
            UnknownSessionError: No such session.
        """
        if session_id not in self._sessions:
            raise UnknownSessionError(session_id)
        state = self._sessions[session_id]
        state.memory[key] = MemoryEntry(value=value, reason=reason)
        return copy.deepcopy(state)

    def forget(self, session_id: str, key: str) -> SessionState:
        """Remove a memory. The other half of a memory's lifecycle.

        Exists because a store with no removal path makes every memory
        permanent by default, and permanence-by-default is how a stale
        preference outlives the situation that produced it. Removing an absent
        key is a no-op: the caller wanted it gone, and it is.

        Raises:
            UnknownSessionError: No such session.
        """
        if session_id not in self._sessions:
            raise UnknownSessionError(session_id)
        state = self._sessions[session_id]
        state.memory.pop(key, None)
        return copy.deepcopy(state)
