"""The authoritative record of what a session is and what happened in it.

This module is the system's single source of truth. When the same fact exists
in more than one place — a runtime local, a returned copy, a future cache —
this is the copy that wins, and every other copy is derived.

State is deliberately split three ways rather than kept as one blob. These are
not three storage choices — they are the three classical kinds of memory, and
they answer different questions:

- **transcript** — *what happened.* Episodic: events in time, append-only,
  ordered.
- **working_state** — *what is being held right now.* Working: scratch for the
  current turn, overwritable, and nothing should assume it survives.
- **memory** — *what is true.* Semantic: facts, keyed, decontextualized from the
  moment they were learned. A memory is a decision, not a byproduct, which is
  why it has its own write path and its own removal path rather than sharing
  ``commit``'s.

Naming them earns its space, because the split otherwise reads as taste and its
consequences look arbitrary. They follow from the kinds:

- Memory is surfaced through the system prompt and never appended to the
  messages, because a fact is not an utterance. In the message list it would
  acquire a position in the conversation that it does not have.
- ``remember`` overwrites where ``commit`` appends. Updating a fact *replaces*
  it — the previous value is not history, it is wrong. Correcting an event means
  appending a correction, because the event still happened. Which is also why
  ``forget`` exists and there is no un-append.
- :class:`MemoryEntry` requires a ``reason`` and :class:`TranscriptItem` does
  not. An event carries its own justification: it sits at a position, among the
  things that led to it. A decontextualized fact carries none, and without the
  reason nobody can review whether "prefers concise answers" still holds.

What is deliberately absent is retrieval. Every memory is surfaced, subject only
to a recency bound in :mod:`bacteria.context.assembly` — there is no relevance
ranking and no query — so this is semantic memory by role and a keyed profile
store by mechanism. Relevance is that module's question, not this one's; this
module owns what is true, not what is worth saying now.

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
    Persistence *here*. Sessions in this implementation live in a process-local
    dict and vanish on exit, so on its own the agent has no cross-session memory
    and no resume after a restart. The seam for a durable one is now explicit:
    :class:`bacteria.session.protocol.SessionRepository` is the complete set of
    operations a backing store must provide, and the runtime depends on that
    protocol rather than on this class. A durable store is therefore an addition
    made by whoever hosts this package, not a change to any caller here. What it
    drags in beyond the backend itself: serialization for
    :class:`TranscriptItem` and :class:`MemoryEntry`, and the concurrency
    control below.

    Concurrency control. ``commit`` assumes it is the only writer, which holds
    for this implementation — a dict mutated between awaits, in one process —
    and stops holding the moment a store is shared. That check belongs inside
    ``commit``, which is why it stays the only write path even though it is
    currently a thin one.

    Worth knowing what a real host had to do, since the shape here suggested
    something else: the application backing this with Postgres did not add a
    version column. It takes a row lock on the session for the duration of the
    write, because its ``seq`` is derived from what it reads, and a staleness
    check would have rejected the second concurrent turn rather than ordering
    it. A store whose positions are assigned by the database may need neither.

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


OWNER = "owner"
"""The source of a memory written by the person who owns the session.

Their writes are active immediately, because the human confirmation every other
source has to wait for *is* them ([ADR 0017](../../docs/adr/0017-memory-is-proposed-and-confirmed.md)).
"""


@dataclass(frozen=True)
class MemoryEntry:
    """One preserved fact, or one proposal that it should become preserved.

    ``reason`` is required, not optional. A memory with no recorded reason
    cannot be reviewed later — there is no way to judge whether it is still
    worth keeping, so it is kept forever by default. Requiring provenance at
    write time is what makes expiry a decision someone can actually make.

    ``source`` says who proposed it — :data:`OWNER`, a model, or a named job.
    It survives activation rather than being discarded once the entry is live,
    because "the extractor has been noisy" is a question someone will ask and
    an activated memory that forgot where it came from cannot answer it.

    There is deliberately no ``status`` field. Whether an entry is proposed or
    active is expressed by *which collection it is in* on
    :class:`SessionState`, not by an attribute that could disagree with its
    container. ADR 0017 as drafted named a status field; making the two
    collections key differently is what forced the change, and the redundancy
    it removes is the kind this package treats as a defect.
    """

    value: Any
    reason: str
    source: str = OWNER
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class SessionState:
    """Everything the store holds for one session.

    Mutable, unlike the items inside it, because ``commit`` mutates it in
    place. Callers never receive this object — only deep copies of it.

    ``memory`` and ``proposals`` are separate collections with *different keys*,
    and that difference is the whole mechanism of ADR 0017:

    - ``memory`` is keyed by ``key`` alone. At most one active fact may claim a
      key, which is what keeps the model's view unambiguous.
    - ``proposals`` is keyed by ``(source, key)``. Two proposers may both
      suggest ``tone`` and both survive, because collapsing them is a judgement
      only a human can make — the same rule the ingestion pipeline applies to
      duplicate records, and for the same reason.

    Only ``memory`` reaches a model. A proposal is inert until something
    activates it.
    """

    session: Session
    transcript: list[TranscriptItem] = field(default_factory=list)
    working_state: dict[str, Any] = field(default_factory=dict)
    memory: dict[str, MemoryEntry] = field(default_factory=dict)
    proposals: dict[tuple[str, str], MemoryEntry] = field(default_factory=dict)


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

    **Why these methods are coroutines when none of them wait for anything.**
    This implementation is a dictionary, so every ``async def`` below wraps
    work that finishes immediately, and in isolation each looks like ceremony.
    The signature belongs to the interface rather than to this implementation:
    the persistence gap above promises that adding a real backend is a second
    implementation of this class and *not a change to any caller*. A synchronous
    interface would make that false the first time the backend was a database —
    every caller would have to grow an ``await``, which is precisely the
    caller-side change the promise rules out. Paying for it once, here, is what
    keeps the seam honest.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, SessionState] = {}

    async def create_session(self, user_id: str) -> Session:
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

    async def get_state(self, session_id: str) -> SessionState:
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

    async def commit(
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

    async def remember(
        self, session_id: str, key: str, value: Any, reason: str, source: str = OWNER
    ) -> SessionState:
        """Record a fact worth re-surfacing later. The only write path for memory.

        Separate from :meth:`commit` on purpose. Routing memory through
        ``working_state_updates`` would make "remember this permanently" and
        "stash this for the current turn" the same call, and the difference
        between them is the entire reason memory exists as a distinct concern.

        Writes an *active* memory directly, with no confirmation step, and that
        is only correct for the session's owner. Confirmation exists to put a
        human between a suggestion and the model's instructions; the owner is
        that human, so requiring them to confirm their own write would be
        ceremony. Everything else proposes — see :meth:`propose`.

        Args:
            key: Overwrites any existing entry. Updating a memory is a write,
                not an append — the transcript is where history lives.
            reason: Why this is worth keeping. Required; see :class:`MemoryEntry`.
            source: Who is writing. Defaults to :data:`OWNER`, and a caller that
                is not the owner should be calling ``propose`` instead. Kept as
                an argument rather than hardcoded so an activated proposal can
                retain the source that suggested it.

        Raises:
            UnknownSessionError: No such session.
        """
        if session_id not in self._sessions:
            raise UnknownSessionError(session_id)
        state = self._sessions[session_id]
        state.memory[key] = MemoryEntry(value=value, reason=reason, source=source)
        return copy.deepcopy(state)

    async def propose(
        self, session_id: str, key: str, value: Any, reason: str, source: str
    ) -> SessionState:
        """Suggest a memory without making one. Reaches no model until activated.

        This is the write path for anything that is not the session's owner —
        a tool the model called, a job that read the transcript. The proposal
        sits in ``proposals`` and is invisible to
        :func:`~bacteria.context.assembly.assemble_context`, so an injected
        instruction stops at a queue a human reads instead of becoming an
        instruction the model follows. That is the whole point of ADR 0017 and
        the reason this is not simply ``remember`` with a flag.

        Keyed by ``(source, key)``, so two proposers may both suggest ``tone``
        and neither silently overwrites the other. Re-proposing the *same*
        source and key does overwrite, which is what makes a retried job safe:
        it replaces its own previous suggestion rather than accumulating copies.

        Raises:
            UnknownSessionError: No such session.
        """
        if session_id not in self._sessions:
            raise UnknownSessionError(session_id)
        state = self._sessions[session_id]
        state.proposals[(source, key)] = MemoryEntry(value=value, reason=reason, source=source)
        return copy.deepcopy(state)

    async def activate(self, session_id: str, source: str, key: str) -> SessionState:
        """Promote a proposal into active memory. The human act.

        Collapsing happens here and only here: the proposal was keyed by
        ``(source, key)`` and the resulting memory is keyed by ``key``, so
        activating one of two competing suggestions resolves the conflict by
        replacing whatever held that key. The person activating is the only
        actor able to judge that, which is why nothing upstream tries.

        The activated entry keeps its ``source``. A memory that forgot it was
        suggested by a job could not later be distrusted as one.

        Raises:
            UnknownSessionError: No such session.
            KeyError: No such proposal. Distinct from activating an already
                active memory, which is not something this method can be asked
                to do — proposals and memories are different collections.
        """
        if session_id not in self._sessions:
            raise UnknownSessionError(session_id)
        state = self._sessions[session_id]
        proposal = state.proposals.pop((source, key))
        # Rebuilt rather than moved, so ``created_at`` becomes the moment of
        # activation. The field drives which memories reach the model — assembly
        # keeps the most recent — and the fact was asserted *now*, by whoever
        # accepted it. Carrying the proposal's timestamp over would let a
        # suggestion made weeks ago be activated today and immediately be at
        # risk of ageing out, which nobody could explain.
        state.memory[key] = MemoryEntry(
            value=proposal.value, reason=proposal.reason, source=proposal.source
        )
        return copy.deepcopy(state)

    async def reject(self, session_id: str, source: str, key: str) -> SessionState:
        """Discard a proposal without it ever becoming a memory.

        A no-op on an absent proposal, matching :meth:`forget`: the caller
        wanted it gone, and it is. Rejection leaves no record here — if "this
        was suggested and refused" needs to be answerable, that belongs in the
        transcript, which is where history lives.

        Raises:
            UnknownSessionError: No such session.
        """
        if session_id not in self._sessions:
            raise UnknownSessionError(session_id)
        state = self._sessions[session_id]
        state.proposals.pop((source, key), None)
        return copy.deepcopy(state)

    async def forget(self, session_id: str, key: str) -> SessionState:
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
