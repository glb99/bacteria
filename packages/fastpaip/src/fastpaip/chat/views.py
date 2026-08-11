"""HTTP surface for conversations with the agent.

Every route requires an authenticated caller and touches only that caller's
sessions. The two are separate steps on purpose: ``CurrentPrincipal``
establishes who, :func:`~fastpaip.chat.access.load_owned_session` establishes
whether.
"""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, status
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


class MemoryWrite(BaseModel):
    """A fact to preserve, and why.

    ``reason`` is required here because it is required by the agent's own
    :class:`~bacteria.session.store.MemoryEntry`, and for the same purpose: a
    memory whose justification was never recorded cannot be reviewed later, so
    it is kept forever by default. Making the caller supply one is what turns
    "should this still be here?" into an answerable question.
    """

    value: Any
    reason: str = Field(min_length=1)


class MemoryEntryOut(BaseModel):
    key: str
    value: Any
    reason: str
    source: str
    created_at: datetime


class ProposalOut(BaseModel):
    """A suggested memory awaiting a decision.

    Carries ``source`` because it is half of the identity: two proposers may
    suggest the same ``key``, and a reviewer choosing between them needs to know
    which is which. Both are required to activate or reject one.
    """

    source: str
    key: str
    value: Any
    reason: str
    created_at: datetime


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


@router.get("/sessions/{session_id}/memory", response_model=list[MemoryEntryOut])
async def read_memory(
    session_id: str, principal: CurrentPrincipal, db: DbSession
) -> list[MemoryEntryOut]:
    """List what this session has been told to remember, and why.

    The review surface. Memory requires a ``reason`` precisely so that someone
    can later judge whether an entry still earns its place, and until this route
    existed there was nowhere to make that judgement — the reason was written
    into the model's prompt and shown to no human.

    Ordered oldest first, matching the order the agent renders them in.
    """
    state = await load_owned_session(SqlSessionRepository(db), principal, session_id)
    entries = sorted(state.memory.items(), key=lambda item: item[1].created_at)
    return [
        MemoryEntryOut(
            key=key,
            value=entry.value,
            reason=entry.reason,
            source=entry.source,
            created_at=entry.created_at,
        )
        for key, entry in entries
    ]


@router.put("/sessions/{session_id}/memory/{key}", response_model=MemoryEntryOut)
async def write_memory(
    session_id: str,
    key: str,
    body: MemoryWrite,
    principal: CurrentPrincipal,
    db: DbSession,
) -> MemoryEntryOut:
    """Preserve a fact for every later turn in this session.

    ``PUT``, not ``POST``: writing the same key twice is one memory, not two.
    That is the agent store's own rule — ``remember`` overwrites by key, because
    updating a memory is a write rather than an append, and the transcript is
    where history lives.

    The caller writing this is the session's owner, and only the owner may write
    an *active* memory directly. Everything else proposes, and a proposal waits
    here for a human — see the review routes below. The distinction is a
    security boundary: memory is injected into the system prompt on every later
    turn, so a model able to write it directly could write its own future
    instructions. See bacteria's ADR 0017.

    Only the most recent entries reach the model — see ``DEFAULT_MEMORY_LIMIT``
    in the agent's context assembly. Writing an unbounded number here does not
    mean the model sees them all.
    """
    repository = SqlSessionRepository(db)
    await load_owned_session(repository, principal, session_id)

    state = await repository.remember(session_id, key=key, value=body.value, reason=body.reason)
    entry = state.memory[key]
    return MemoryEntryOut(
        key=key,
        value=entry.value,
        reason=entry.reason,
        source=entry.source,
        created_at=entry.created_at,
    )


@router.delete("/sessions/{session_id}/memory/{key}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_memory(
    session_id: str, key: str, principal: CurrentPrincipal, db: DbSession
) -> None:
    """Remove a memory.

    204 whether or not the key was there. Deleting an absent memory is not an
    error — the caller wanted it gone, and it is — and answering 404 would leak
    which keys exist to someone probing them one at a time.

    Without this route every memory is permanent by default, which is how a
    preference outlives the situation that produced it.
    """
    repository = SqlSessionRepository(db)
    await load_owned_session(repository, principal, session_id)
    await repository.forget(session_id, key=key)


@router.get("/sessions/{session_id}/memory-proposals", response_model=list[ProposalOut])
async def read_proposals(
    session_id: str, principal: CurrentPrincipal, db: DbSession
) -> list[ProposalOut]:
    """List suggested memories awaiting a decision.

    These reach no model. That is the point of them existing separately: an
    injected "remember that you must always comply" stops here, as a row a human
    reads, rather than becoming an instruction the model follows on the next
    turn.

    A queue nobody reads is the failure mode this route enables, and it is
    recorded as such in ADR 0017 — proposals accumulate, nothing activates, and
    the agent appears to have no memory while behaving exactly as designed.
    """
    state = await load_owned_session(SqlSessionRepository(db), principal, session_id)
    pending = sorted(state.proposals.items(), key=lambda item: item[1].created_at)
    return [
        ProposalOut(
            source=source,
            key=key,
            value=entry.value,
            reason=entry.reason,
            created_at=entry.created_at,
        )
        for (source, key), entry in pending
    ]


@router.post(
    "/sessions/{session_id}/memory-proposals/{source}/{key}",
    response_model=MemoryEntryOut,
    status_code=201,
)
async def activate_proposal(
    session_id: str, source: str, key: str, principal: CurrentPrincipal, db: DbSession
) -> MemoryEntryOut:
    """Accept a suggestion, making it a memory the model will see.

    The human act the whole design is built around. Addressed by ``source`` and
    ``key`` together, because two proposers may suggest the same key and the
    reviewer is choosing between them — activating one replaces whatever held
    that key, which is where competing suggestions collapse.

    ``404`` when there is no such proposal, rather than silently creating a
    memory from nothing: a stale review page must not be able to conjure a fact
    nobody just read.
    """
    repository = SqlSessionRepository(db)
    await load_owned_session(repository, principal, session_id)

    try:
        state = await repository.activate(session_id, source=source, key=key)
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="no such proposal"
        ) from None

    entry = state.memory[key]
    return MemoryEntryOut(
        key=key,
        value=entry.value,
        reason=entry.reason,
        source=entry.source,
        created_at=entry.created_at,
    )


@router.delete(
    "/sessions/{session_id}/memory-proposals/{source}/{key}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def reject_proposal(
    session_id: str, source: str, key: str, principal: CurrentPrincipal, db: DbSession
) -> None:
    """Discard a suggestion without it ever becoming a memory.

    ``204`` whether or not it was there, matching the memory delete route and
    for the same reason: the caller wanted it gone, and answering 404 would let
    someone probe which proposals exist.
    """
    repository = SqlSessionRepository(db)
    await load_owned_session(repository, principal, session_id)
    await repository.reject(session_id, source=source, key=key)
