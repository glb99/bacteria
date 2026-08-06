"""HTTP surface for conversations with the agent."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from bacteria.session.store import UnknownSessionError

from fastpaip.chat.repository import SqlSessionRepository
from fastpaip.chat.service import run_turn
from fastpaip.core.dependencies import AppSettings, DbSession

router = APIRouter(prefix="/chat", tags=["chat"])


class NewSession(BaseModel):
    user_id: str = Field(min_length=1)


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
async def create_session(body: NewSession, db: DbSession) -> SessionCreated:
    session = await SqlSessionRepository(db).create_session(user_id=body.user_id)
    return SessionCreated(session_id=session.session_id, user_id=session.user_id)


@router.post("/sessions/{session_id}/turns", response_model=TurnResult)
async def take_turn(
    session_id: str, body: Turn, db: DbSession, settings: AppSettings
) -> TurnResult:
    """Advance the conversation by one turn.

    A failed turn still returns 5xx *after* the agent has committed its evidence
    — the runtime writes the user's message and the error to the transcript
    before the exception escapes, so a caller retrying can see what already
    happened rather than finding a gap.
    """
    try:
        result = await run_turn(
            repository=SqlSessionRepository(db),
            provider=settings.model_provider,
            session_id=session_id,
            user_text=body.text,
        )
    except UnknownSessionError:
        raise HTTPException(status_code=404, detail="no such session") from None

    return TurnResult(run_id=result.run_id, reply=result.response.text)


@router.get("/sessions/{session_id}/transcript", response_model=list[TranscriptEntry])
async def read_transcript(session_id: str, db: DbSession) -> list[TranscriptEntry]:
    try:
        state = await SqlSessionRepository(db).get_state(session_id)
    except UnknownSessionError:
        raise HTTPException(status_code=404, detail="no such session") from None

    return [TranscriptEntry(kind=i.kind, payload=i.payload) for i in state.transcript]
