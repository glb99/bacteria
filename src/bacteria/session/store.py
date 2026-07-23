"""Session/state store — Part 3 (Control Planes, Sessions, and State Ownership).

Owns the authoritative record for a session. Transcript, working state, and
memory are kept as separate concerns, per the article's "state hides three
different jobs" distinction. Callers never mutate state directly: SessionStore
.commit() is the only code path allowed to write, taking the candidate change
as plain arguments rather than a separate proposal object — a single method,
not two, is enough to keep the model/runtime's output a proposal rather than
a direct write (Part 3 decision); see docs/SYSTEM_DESIGN.md Part 4 discussion
for why the earlier propose()/commit() split was collapsed.

Memory (durable, cross-session state) is intentionally left as a stub here —
its real design belongs to Part 5 (Context, Retrieval, and Memory).
"""

from __future__ import annotations

import copy
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

TranscriptItemKind = Literal["message", "tool_call", "tool_result", "approval"]


@dataclass(frozen=True)
class Session:
    session_id: str
    user_id: str
    created_at: datetime


@dataclass(frozen=True)
class TranscriptItem:
    kind: TranscriptItemKind
    payload: dict[str, Any]
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class SessionState:
    session: Session
    transcript: list[TranscriptItem] = field(default_factory=list)
    working_state: dict[str, Any] = field(default_factory=dict)
    # Memory stub: revisit in Part 5. Not read or written by anything yet.
    memory: dict[str, Any] = field(default_factory=dict)


class UnknownSessionError(KeyError):
    pass


class SessionStore:
    """The single authoritative source of truth for session state.

    In-memory only for now — durability across process restarts is explicitly
    deferred to Part 4 (Runtimes, Workflows, and Durable Execution).
    """

    def __init__(self) -> None:
        self._sessions: dict[str, SessionState] = {}

    def create_session(self, user_id: str) -> Session:
        session = Session(
            session_id=str(uuid.uuid4()),
            user_id=user_id,
            created_at=datetime.now(timezone.utc),
        )
        self._sessions[session.session_id] = SessionState(session=session)
        return session

    def get_state(self, session_id: str) -> SessionState:
        """Returns a deep copy — callers cannot mutate the authoritative record this way."""
        if session_id not in self._sessions:
            raise UnknownSessionError(session_id)
        return copy.deepcopy(self._sessions[session_id])

    def commit(
        self,
        session_id: str,
        new_transcript_items: list[TranscriptItem] | None = None,
        working_state_updates: dict[str, Any] | None = None,
    ) -> SessionState:
        """The only method allowed to mutate authoritative state.

        Takes the candidate change directly rather than a separate proposal
        object — still a proposal conceptually (nothing is authoritative
        until this method applies it), just not a distinct public step. A
        future staleness/conflict check would live inside this method.
        """
        if session_id not in self._sessions:
            raise UnknownSessionError(session_id)
        state = self._sessions[session_id]
        state.transcript.extend(new_transcript_items or [])
        state.working_state.update(working_state_updates or {})
        return copy.deepcopy(state)
