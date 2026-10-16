import copy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal, Protocol
import uuid

from agent.errors import UnknownSessionError


TranscriptItemKind = Literal["message", "tool_call", "run_error"]


@dataclass
class Session:
    session_id: str


@dataclass
class SessionState:
    session: Session


@dataclass
class SessionState:
    session: Session
    transcript: list[TranscriptItem] = field(default_factory=list)


@dataclass(frozen=True)
class TranscriptItem:
    """One immutable entry in the durable record.

    Frozen because the transcript is append-only: correcting history means
    appending a correction, not editing what was already recorded.

    Attributes:
        run_id: Which run wrote this, or ``None``. A field rather than a
            ``payload`` key because ``payload`` differs per ``kind`` and this
            does not, and because "everything from run X" should be an index
            scan rather than a reach into JSON.

            Optional because not every write is a run — a working-state-only
            commit is not one, and rows written before the field existed have
            no run to name. Neither gets a fabricated id. What that costs is
            that a producer forgetting to set it fails silently, so the
            runtime's obligation to stamp every item it commits is asserted by
            a test rather than by this type. See
            [ADR 0018](../../docs/adr/0018-transcript-items-carry-their-run-id.md).
    """

    kind: TranscriptItemKind
    payload: dict[str, Any]
    timestamp: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc))
    run_id: str | None = None


TranscriptiontemKind = Literal["message", "tool_call", "run_error"]


class SessionRepository(Protocol):
    def get_state(self, session_id: str) -> SessionState:
        # Implement the logic to retrieve the session state from a database or in-memory store
        pass

    def create_session(self) -> Session:
        # Implement the logic to create a new session in the repository
        pass

    def commit(self, session_id: str, new_transcript_item: TranscriptItem) -> None:
        # Implement the logic to commit a new transcript item to the session state
        pass


class InMemorySessionRepository:
    def __init__(self):
        self._sessions: dict[str, SessionState] = {}

    def get_state(self, session_id: str) -> SessionState:
        if session_id not in self._sessions:
            raise UnknownSessionError(session_id)
        return self._detached(self._sessions[session_id])

    def create_session(self) -> Session:
        session = Session(
            session_id=str(uuid.uuid4()),
        )
        self._sessions[session.session_id] = SessionState(session=session)
        return session

    def _detached(self, state: SessionState) -> SessionState:
        """Copy ``state``, with the owner's user memory folded in.

        User memory is stored per user and handed back per session, so this is
        the one place the two views are joined. Doing it on read rather than on
        write means a memory written in one session is visible in another
        immediately, without anything having to fan the write out.
        """
        detached = copy.deepcopy(state)
        return detached

    def commit(self, session_id: str, new_transcript_item: TranscriptItem) -> None:
        if session_id not in self._sessions:
            raise UnknownSessionError(session_id)
        self._sessions[session_id].transcript.append(new_transcript_item)
