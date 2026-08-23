"""HTTP surface for conversations with the agent.

Every route requires an authenticated caller and touches only that caller's
sessions. The two are separate steps on purpose: ``CurrentPrincipal``
establishes who, :func:`~bacteria.app.chat.access.load_owned_session` establishes
whether.

**One route does not use the second step, and cannot.** ``GET /sessions`` has no
session id to establish anything about; ownership there is a filter rather than
a check. The difference matters because the two fail in opposite directions — a
broken check refuses a legitimate caller, a broken filter hands over everyone
else's conversations — so that route asserts its refusal in
`test_chat_access.py` rather than trusting the shape.
"""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from bacteria.agent.session.store import SESSION_SCOPE, USER_SCOPE, MemoryScope
from bacteria.app.auth.dependencies import CurrentPrincipal
from bacteria.app.chat import review
from bacteria.app.chat.access import load_owned_session
from bacteria.app.chat.repository import SqlSessionRepository
from bacteria.app.chat.service import run_turn
from bacteria.app.core.dependencies import AppSettings, DbSession

router = APIRouter(prefix="/chat", tags=["chat"])


class SessionCreated(BaseModel):
    session_id: str
    user_id: str


class SessionSummaryOut(BaseModel):
    """One line in a session picker.

    No ``user_id``: every session in the response belongs to the caller, so a
    per-row owner would be a constant field that reads like it could vary.
    """

    session_id: str
    created_at: datetime
    last_activity_at: datetime


class ExtractionProgressOut(BaseModel):
    """How far memory extraction has read this conversation.

    ``behind`` is served rather than left as arithmetic for the client: both
    positions start at ``-1``, so subtracting them on a fresh session is right
    only by accident.
    """

    through_seq: int
    latest_seq: int
    behind: int


class Turn(BaseModel):
    text: str = Field(min_length=1)


class TurnResult(BaseModel):
    run_id: str
    reply: str | None


class TranscriptEntry(BaseModel):
    """One thing that happened in a conversation, as a reader sees it.

    ``run_id`` and ``timestamp`` are carried because a reader needs them and the
    layer below already had them. Without the first, the items belonging to one
    turn -- the user message, the tool calls, the reply, the `run_meta` -- are an
    undifferentiated list; without the second, nothing can say when. Both are on
    :class:`~bacteria.agent.session.store.TranscriptItem` and were simply not
    exposed, so this widens a projection rather than adding a record.

    ``seq`` is deliberately absent, and its absence is not an oversight to fix
    here. The database orders by it, but the agent's dataclass does not carry
    it, so surfacing it would mean widening a type in a vendorable package to
    serve one screen. The list arrives in order, which is what a reader actually
    needs; the extraction route reports the real ``seq`` where it means
    something.

    ``run_id`` is optional because it genuinely is: items written outside a run
    have none.
    """

    kind: str
    payload: dict
    run_id: str | None
    timestamp: datetime


class MemoryWrite(BaseModel):
    """A fact to preserve, and why.

    ``reason`` is required here because it is required by the agent's own
    :class:`~bacteria.agent.session.store.MemoryEntry`, and for the same purpose: a
    memory whose justification was never recorded cannot be reviewed later, so
    it is kept forever by default. Making the caller supply one is what turns
    "should this still be here?" into an answerable question.
    """

    value: Any
    reason: str = Field(min_length=1)


class MemoryEntryOut(BaseModel):
    """One stored fact, with enough to judge and to delete it.

    ``scope`` is here because ``key`` alone no longer identifies an entry: a
    standing preference and this conversation's override of it share a key and
    are different rows. A reviewer deleting one has to say which.
    """

    key: str
    value: Any
    reason: str
    source: str
    scope: MemoryScope
    created_at: datetime


class HeldOut(BaseModel):
    """An active memory a proposal would displace, and what it currently says.

    The value is carried, not just the scope. Warning that something will be
    replaced without saying what is a note that reads as informative and decides
    nothing -- recorded in :class:`~bacteria.app.chat.review.Held` from a review
    walk where it cost a good value.
    """

    scope: MemoryScope
    value: Any


class ProposalOut(BaseModel):
    """A suggested memory awaiting a decision.

    Carries ``source`` because it is half of the identity: two proposers may
    suggest the same ``key``, and a reviewer choosing between them needs to know
    which is which. Both are required to activate or reject one.

    ``held_by`` is what makes that choice an informed one. Proposals are keyed by
    ``(source, key)`` and active memory by ``key`` alone, so accepting a second
    suggestion for a key *replaces* the first rather than joining it. Two
    proposers agreeing on a key is the ordinary case rather than a corner one --
    ``known_keys`` deliberately pushes the extractor towards keys already in use,
    so "my name is Guillermo" routinely produces both ``("model", "name")`` and
    ``("extractor", "name")`` -- and the collapse between them is invisible
    unless the listing says so *before* the decision instead of after.

    Empty for a proposal whose key nothing active holds, which is the common
    case and the one where accepting costs nothing.
    """

    source: str
    key: str
    value: Any
    reason: str
    created_at: datetime
    held_by: list[HeldOut] = []


@router.get("/sessions", response_model=list[SessionSummaryOut])
async def list_sessions(principal: CurrentPrincipal, db: DbSession) -> list[SessionSummaryOut]:
    """Every conversation the caller owns, most recently active first.

    **The principal is the filter, and the client cannot influence it.** There
    is no ``user_id`` parameter and there must not be one: this route returns a
    set rather than a named resource, so there is nothing for
    :func:`load_owned_session` to check afterwards, and a query parameter here
    would be the same mistake ``create_session`` records — accepting an owner
    from the caller and then serving it entirely legitimately.

    Returns everything, unpaginated, matching the repository's own note about
    transcripts: it is bounded by how many conversations one principal has
    opened, which is a number nobody has yet made large.
    """
    summaries = await SqlSessionRepository(db).list_sessions(principal.id)
    return [
        SessionSummaryOut(
            session_id=summary.session_id,
            created_at=summary.created_at,
            last_activity_at=summary.last_activity_at,
        )
        for summary in summaries
    ]


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
    # Check ownership, only for exception in case
    await load_owned_session(repository, principal, session_id)

    result = await run_turn(
        repository=repository,
        provider=settings.model_provider,
        session_id=session_id,
        user_text=body.text,
        # `.id`, not the whole principal: it is what resources are owned by and
        # what outlives a credential, so it is the identifier a later reader can
        # still resolve. Passing the object would put a credential's details one
        # attribute away from a span.
        principal=principal.id,
        extract=settings.memory_extraction_enabled,
        build_graph=settings.graph_extraction_enabled,
    )
    return TurnResult(run_id=result.run_id, reply=result.response.text)


@router.get("/sessions/{session_id}/transcript", response_model=list[TranscriptEntry])
async def read_transcript(
    session_id: str, principal: CurrentPrincipal, db: DbSession
) -> list[TranscriptEntry]:
    state = await load_owned_session(SqlSessionRepository(db), principal, session_id)
    return [
        TranscriptEntry(
            kind=item.kind,
            payload=item.payload,
            run_id=item.run_id,
            timestamp=item.timestamp,
        )
        for item in state.transcript
    ]


@router.get("/sessions/{session_id}/extraction", response_model=ExtractionProgressOut)
async def read_extraction_progress(
    session_id: str, principal: CurrentPrincipal, db: DbSession
) -> ExtractionProgressOut:
    """Whether the memory extractor has kept up with this conversation.

    The question that was only answerable by opening psql, and it was asked in
    anger: a deployment ran for an afternoon with no worker, and the symptom was
    proposals never appearing while everything else looked healthy. A watermark
    that has stopped moving while ``latest_seq`` climbs is that failure, visible.

    Answers for a session with extraction switched off too, and truthfully —
    ``behind`` grows, because the transcript is genuinely unread. This route
    reports the queue's state, not the configuration's intent.
    """
    repository = SqlSessionRepository(db)
    await load_owned_session(repository, principal, session_id)

    progress = await repository.extraction_progress(session_id)
    return ExtractionProgressOut(
        through_seq=progress.through_seq,
        latest_seq=progress.latest_seq,
        behind=progress.behind,
    )


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
    # Both scopes, each labelled, including an entry currently shadowed by a
    # session-scoped one on the same key. The reviewer is judging what is stored
    # rather than what this turn renders, and hiding the loser would make a
    # memory they can still delete invisible to them.
    scoped = [(SESSION_SCOPE, state.memory), (USER_SCOPE, state.user_memory)]
    entries = sorted(
        ((scope, key, entry) for scope, memory in scoped for key, entry in memory.items()),
        key=lambda row: row[2].created_at,
    )
    return [
        MemoryEntryOut(
            key=key,
            value=entry.value,
            reason=entry.reason,
            source=entry.source,
            scope=scope,
            created_at=entry.created_at,
        )
        for scope, key, entry in entries
    ]


@router.put("/sessions/{session_id}/memory/{key}", response_model=MemoryEntryOut)
async def write_memory(
    session_id: str,
    key: str,
    body: MemoryWrite,
    principal: CurrentPrincipal,
    db: DbSession,
    scope: MemoryScope = SESSION_SCOPE,
) -> MemoryEntryOut:
    """Preserve a fact for this session, or for the caller everywhere.

    ``?scope=user`` writes a memory that outlives this conversation and reaches
    every session this principal opens. It defaults to ``session``, which is the
    conservative one: the wider blast radius should be the choice someone made
    rather than the one they got.

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

    entry = await repository.remember(
        session_id, key=key, value=body.value, reason=body.reason, scope=scope
    )
    return MemoryEntryOut(
        key=key,
        value=entry.value,
        reason=entry.reason,
        source=entry.source,
        scope=scope,
        created_at=entry.created_at,
    )


@router.delete("/sessions/{session_id}/memory/{key}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_memory(
    session_id: str,
    key: str,
    principal: CurrentPrincipal,
    db: DbSession,
    scope: MemoryScope = SESSION_SCOPE,
) -> None:
    """Remove a memory from one scope.

    Scoped rather than removing both, because dropping a session's override of a
    standing preference should leave the standing one — those are different
    intentions and one call cannot mean both.

    204 whether or not the key was there. Deleting an absent memory is not an
    error — the caller wanted it gone, and it is — and answering 404 would leak
    which keys exist to someone probing them one at a time.

    Without this route every memory is permanent by default, which is how a
    preference outlives the situation that produced it.
    """
    repository = SqlSessionRepository(db)
    await load_owned_session(repository, principal, session_id)
    await repository.forget(session_id, key=key, scope=scope)


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

    Built through :func:`~bacteria.app.chat.review.pending_from` rather than by
    reading ``state.proposals`` here, and that was a real gap rather than tidying.
    ``held_by`` — what accepting a proposal would replace — existed only in the
    admin CLI's review walk, so the console listed two suggestions for one key as
    two independent rows: accepting either silently overwrote the other, and
    accepting both meant the second undid the first. One computation, both
    surfaces, because two surfaces deriving it separately is how they come to
    disagree about what a decision costs.
    """
    state = await load_owned_session(SqlSessionRepository(db), principal, session_id)

    # Oldest first, not the ``(source, key)`` order the listing is built in. A
    # review queue is worked through in the order things arrived; the grouping of
    # rivals is `held_by`'s job and does not need them adjacent.
    entries = sorted(review.pending_from(state).entries, key=lambda entry: entry.created_at)
    return [
        ProposalOut(
            source=entry.source,
            key=entry.key,
            value=entry.value,
            reason=entry.reason,
            created_at=entry.created_at,
            held_by=[HeldOut(scope=held.scope, value=held.value) for held in entry.held_by],
        )
        for entry in entries
    ]


@router.post(
    "/sessions/{session_id}/memory-proposals/{source}/{key}",
    response_model=MemoryEntryOut,
    status_code=201,
)
async def activate_proposal(
    session_id: str,
    source: str,
    key: str,
    principal: CurrentPrincipal,
    db: DbSession,
    scope: MemoryScope = SESSION_SCOPE,
) -> MemoryEntryOut:
    """Accept a suggestion, making it a memory the model will see.

    ``?scope=user`` accepts it for every future conversation. The scope is
    chosen *here*, by the person accepting, and never carried on the proposal:
    a model able to mark its own suggestion user-scoped would be deciding that
    something it wrote applies to everything that person does later.

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
        entry = await repository.activate(session_id, source=source, key=key, scope=scope)
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="no such proposal"
        ) from None

    return MemoryEntryOut(
        key=key,
        value=entry.value,
        reason=entry.reason,
        source=entry.source,
        scope=scope,
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
