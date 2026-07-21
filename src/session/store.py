"""Session/state store — Part 3 (Control Planes, Sessions, and State Ownership).

Owns the authoritative record for a session. Transcript, working state, and
memory are kept as separate concerns, per the article's "state hides three
different jobs" distinction. Callers never mutate state directly: they build
a StateMutationProposal and hand it to SessionStore.commit(), which is the
only code path allowed to write. This keeps the model/runtime's output a
proposal, never a direct write (Part 3 decision).

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


@dataclass
class StateMutationProposal:
    """A candidate set of changes. Not authoritative until SessionStore.commit()."""

    session_id: str
    new_transcript_items: list[TranscriptItem] = field(default_factory=list)
    working_state_updates: dict[str, Any] = field(default_factory=dict)


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

    def propose(
        self,
        session_id: str,
        new_transcript_items: list[TranscriptItem] | None = None,
        working_state_updates: dict[str, Any] | None = None,
    ) -> StateMutationProposal:
        if session_id not in self._sessions:
            raise UnknownSessionError(session_id)
        return StateMutationProposal(
            session_id=session_id,
            new_transcript_items=list(new_transcript_items or []),
            working_state_updates=dict(working_state_updates or {}),
        )

    def commit(self, proposal: StateMutationProposal) -> SessionState:
        """The only method allowed to mutate authoritative state."""
        if proposal.session_id not in self._sessions:
            raise UnknownSessionError(proposal.session_id)
        state = self._sessions[proposal.session_id]
        state.transcript.extend(proposal.new_transcript_items)
        state.working_state.update(proposal.working_state_updates)
        return copy.deepcopy(state)
