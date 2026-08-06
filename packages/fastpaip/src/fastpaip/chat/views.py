"""HTTP surface for conversations with the agent.

Every route requires an authenticated caller and touches only that caller's
sessions. The two are separate steps on purpose: ``CurrentPrincipal``
establishes who, :func:`~fastpaip.chat.access.load_owned_session` establishes
whether.
"""

from fastapi import APIRouter
from pydantic import BaseModel, Field

from fastpaip.auth.dependencies import CurrentPrincipal
from fastpaip.chat.access import load_owned_session
from fastpaip.chat.repository import SqlSessionRepository
from fastpaip.chat.service import run_turn
from fastpaip.core.dependencies import AppSettings, DbSession

router = APIRouter(prefix="/chat", tags=["chat"])


class SessionCreated(BaseModel):
    session_id: str
    user_id: str


class Turn(BaseModel):
    text: str = Field(min_length=1)


class TurnResult(BaseModel):
    run_id: str
    reply: str | None


class TranscriptEntry(BaseModel):
    kind: str
    payload: dict


@router.post("/sessions", response_model=SessionCreated, status_code=201)
async def create_session(principal: CurrentPrincipal, db: DbSession) -> SessionCreated:
    """Open a session owned by the caller.

    Takes no body. The owner is the authenticated principal and cannot be named
    by the client — an earlier version accepted ``user_id`` in the request,
    which meant anyone could create a session as anyone, and then read it
    entirely legitimately.
    """
    session = await SqlSessionRepository(db).create_session(user_id=principal.id)
    return SessionCreated(session_id=session.session_id, user_id=session.user_id)


@router.post("/sessions/{session_id}/turns", response_model=TurnResult)
async def take_turn(
    session_id: str,
    body: Turn,
    principal: CurrentPrincipal,
    db: DbSession,
    settings: AppSettings,
) -> TurnResult:
    """Advance the conversation by one turn.

    Ownership is checked before the model is called, not after. A turn costs
    money and writes to the transcript; refusing afterwards would let an
    unauthorized caller do both and merely not see the reply.

    A failed turn still returns 5xx *after* the agent has committed its evidence
    — the runtime writes the user's message and the error to the transcript
    before the exception escapes, so a caller retrying can see what already
    happened rather than finding a gap.
    """
    repository = SqlSessionRepository(db)
    await load_owned_session(repository, principal, session_id)

    result = await run_turn(
        repository=repository,
        provider=settings.model_provider,
        session_id=session_id,
        user_text=body.text,
    )
    return TurnResult(run_id=result.run_id, reply=result.response.text)


@router.get("/sessions/{session_id}/transcript", response_model=list[TranscriptEntry])
async def read_transcript(
    session_id: str, principal: CurrentPrincipal, db: DbSession
) -> list[TranscriptEntry]:
    state = await load_owned_session(SqlSessionRepository(db), principal, session_id)
    return [TranscriptEntry(kind=i.kind, payload=i.payload) for i in state.transcript]
