"""Deciding what happens to a suggested memory, without saying anything out loud.

The review workflow the agent's ADR 0017 requires a host to supply: listing what
is waiting, activating one, rejecting one. That record specifies the state model
and leaves the workflow to whoever hosts the agent, which is this.

**Nothing here prints or reads input.** Every function returns a value describing
what happened, and the surfaces — the HTTP routes, the admin CLI — turn that into
a response body or a line of terminal output. That split is the point of the
module existing rather than the code living in an entrypoint: `entrypoints/` is
omitted from coverage on the grounds that it holds configuration and no logic,
so a decision made there is a decision nothing tests and the omission quietly
stops being justified.

**Outcomes are returned, not raised.** ``UnknownSessionError`` subclasses
``KeyError``, and the store raises both — a missing session and a missing
proposal are indistinguishable to a caller that gets the ordering wrong, and
getting it wrong reports "no such proposal" for a session that does not exist.
Mapping them once, here, means no caller has to know that inheritance exists.

Parsing lives here too, next to what it dispatches to. It decides between
reviewing and conversing, which is a decision about the system rather than about
how a terminal is drawn.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping

from bacteria.agent.session.store import (
    SESSION_SCOPE,
    USER_SCOPE,
    MemoryEntry,
    MemoryScope,
    SessionState,
    UnknownSessionError,
)
from bacteria.app.personal.repository import SqlSessionRepository

SCOPES: tuple[MemoryScope, ...] = (SESSION_SCOPE, USER_SCOPE)
"""The scopes a person may activate into, in the order they are offered.

Session first because it is the default and the conservative one: a user-scoped
memory applies to every future conversation that person has, which is the point
of memory and also the wider blast radius (the agent's ADR 0021).
"""


# --- What a review surface is told -------------------------------------------


@dataclass(frozen=True)
class Held:
    """An active memory a proposal would displace, and what it currently says.

    The value is carried, not just the scope, and that was learned from a walk
    that went wrong. Told only *that* something would be replaced, a reviewer
    accepted the extractor's ``dad_name = "Pedro"`` at user scope and then, two
    entries later, the model's ``dad_name = "Your dad's name is Pedro."`` — a
    strictly worse phrasing of the same fact, silently promoted over the good
    one. The note was correct and useless: replacement is only a cost if you can
    see what is being lost, and nothing else recovers it once the write lands.
    """

    scope: MemoryScope
    value: Any


@dataclass(frozen=True)
class PendingEntry:
    """One suggestion, with what accepting it would cost.

    ``held_by`` names the scopes whose *active* memory already claims this key,
    and what each holds. It is the part of a listing worth computing: proposals
    are keyed by ``(source, key)`` and active memory by ``key`` alone, so
    accepting a second suggestion for a key replaces the first rather than
    joining it. That collapse is deliberate — ADR 0017 puts it at activation,
    where a human is — and it is invisible unless something says so *before* the
    choice instead of after.
    """

    source: str
    key: str
    value: Any
    reason: str
    created_at: datetime
    held_by: tuple[Held, ...] = ()


@dataclass(frozen=True)
class Pending:
    """Everything awaiting a decision in one session."""

    entries: tuple[PendingEntry, ...] = ()

    def __len__(self) -> int:
        return len(self.entries)


def held_now(entry: PendingEntry, activated: Mapping[str, Held]) -> tuple[Held, ...]:
    """What holds this entry's key, counting decisions taken since the listing.

    A walk reads the queue once and then asks about each entry in turn, so its
    `held_by` is a snapshot from before the reviewer answered anything. Two
    proposals for one key in the same walk is the ordinary case rather than a
    corner one — two proposers finding the same fact is what ADR 0017 expects —
    and by the second one the first has already been activated. Shown the stale
    snapshot, the reviewer is told nothing will be replaced at the exact moment
    something will be.

    ``activated`` maps a key to what the walk just put there. Only additions:
    activating adds a scope and rejecting removes none, so nothing here has to
    model a decision being undone. A scope already in ``held_by`` is *replaced*
    rather than kept — the walk's own write is the newer of the two, and showing
    the snapshot's value would name something that is already gone.

    Pure, and separate from the walk that calls it, because "what would this
    replace" is what a person decides on rather than how a terminal draws it.
    """
    by_scope = {held.scope: held.value for held in entry.held_by}
    just_activated = activated.get(entry.key)
    if just_activated is not None:
        by_scope[just_activated.scope] = just_activated.value
    return tuple(Held(scope, by_scope[scope]) for scope in SCOPES if scope in by_scope)


@dataclass(frozen=True)
class NoSuchSession:
    """The session id does not resolve. Not the same as a session with nothing in it."""

    session_id: str


@dataclass(frozen=True)
class NoSuchProposal:
    """Nothing is waiting under that source and key."""

    source: str
    key: str


@dataclass(frozen=True)
class Accepted:
    """A proposal became a memory the model will be told about."""

    key: str
    scope: MemoryScope
    entry: MemoryEntry


@dataclass(frozen=True)
class Discarded:
    """A proposal is gone.

    ``present`` says whether there was anything to remove. Rejecting is
    idempotent by design — "the caller wanted it gone, and it is" — so this is
    reported rather than made an error, and a surface may still choose to
    mention that nothing matched.
    """

    source: str
    key: str
    present: bool


# --- The operations ----------------------------------------------------------


def pending_from(state: SessionState) -> Pending:
    """The listing, computed from a state a caller already holds.

    Separate from :func:`pending` because the HTTP surface loads the same state
    for a different reason -- ``load_owned_session`` reads it to check ownership
    -- and asking the repository for it again would be a second read of a thing
    already in hand. That is the whole reason this is a function rather than a
    step inside the one below.

    It is also the part worth being pure. ``held_by`` is the answer to "what
    would accepting this destroy", and it is derived entirely from the state: no
    surface should be computing it, and two surfaces computing it separately is
    how they come to disagree.
    """
    active = {SESSION_SCOPE: state.memory, USER_SCOPE: state.user_memory}
    return Pending(
        tuple(
            PendingEntry(
                source=source,
                key=key,
                value=entry.value,
                reason=entry.reason,
                created_at=entry.created_at,
                held_by=tuple(
                    Held(scope, active[scope][key].value)
                    for scope in SCOPES
                    if key in active[scope]
                ),
            )
            for (source, key), entry in sorted(state.proposals.items())
        )
    )


async def pending(repository: SqlSessionRepository, session_id: str) -> Pending | NoSuchSession:
    """What is waiting for a decision, and what each one would replace."""
    try:
        state = await repository.get_state(session_id)
    except UnknownSessionError:
        return NoSuchSession(session_id)

    return pending_from(state)


async def accept(
    repository: SqlSessionRepository,
    session_id: str,
    source: str,
    key: str,
    scope: MemoryScope = SESSION_SCOPE,
) -> Accepted | NoSuchSession | NoSuchProposal:
    """Promote a proposal into active memory at the scope the caller chose."""
    try:
        entry = await repository.activate(session_id, source=source, key=key, scope=scope)
    # Before the bare KeyError and not interchangeable with it: the store raises
    # `UnknownSessionError`, which *subclasses* KeyError, so the other order
    # reports a missing proposal for a session that was never there.
    except UnknownSessionError:
        return NoSuchSession(session_id)
    except KeyError:
        return NoSuchProposal(source, key)

    return Accepted(key=key, scope=scope, entry=entry)


async def discard(
    repository: SqlSessionRepository, session_id: str, source: str, key: str
) -> Discarded | NoSuchSession:
    """Remove a proposal so it stops appearing for review."""
    try:
        state = await repository.get_state(session_id)
    except UnknownSessionError:
        return NoSuchSession(session_id)

    present = (source, key) in state.proposals
    await repository.reject(session_id, source=source, key=key)
    return Discarded(source=source, key=key, present=present)


# --- Reading a line someone typed --------------------------------------------


@dataclass(frozen=True)
class SendMessage:
    """The line is for the model. Carries the text to send, which may differ."""

    text: str


@dataclass(frozen=True)
class ListPending:
    """Show what is waiting."""


@dataclass(frozen=True)
class ReviewEach:
    """Walk the queue, deciding one proposal at a time."""


@dataclass(frozen=True)
class AcceptOne:
    source: str
    key: str
    scope: MemoryScope


@dataclass(frozen=True)
class DiscardOne:
    source: str
    key: str


@dataclass(frozen=True)
class ShowHelp:
    """Print the command list. ``detail`` says what was wrong, if anything."""

    detail: str = ""


ConsoleCommand = SendMessage | ListPending | ReviewEach | AcceptOne | DiscardOne | ShowHelp


def parse_console_line(line: str) -> ConsoleCommand:
    """Decide whether a typed line reviews something or is meant for the model.

    Whitespace-split words and no argument parser, deliberately. A review
    command has a fixed shape, and a line the user typed for a *model* is
    ordinary prose that must never be mangled by quoting rules.

    An unrecognized ``/command`` asks for help rather than becoming a message.
    Nobody types ``/acccept`` meaning to say it out loud, and forwarding it would
    spend a turn on a typo.

    ``//`` escapes, so a message that genuinely begins with a slash is still
    sendable — the one case where refusing to relay what someone typed would be
    the wrong behaviour rather than a helpful one.
    """
    if line.startswith("//"):
        return SendMessage(line[1:])
    if not line.startswith("/"):
        return SendMessage(line)

    name, *rest = line.split()

    if name == "/proposals" and not rest:
        return ListPending()

    if name == "/review" and not rest:
        return ReviewEach()

    if name == "/accept" and len(rest) in (2, 3):
        scope = rest[2] if len(rest) == 3 else SESSION_SCOPE
        if scope not in SCOPES:
            return ShowHelp(f"scope must be one of: {', '.join(SCOPES)}")
        # The membership test above is what makes this a `MemoryScope`, and the
        # checker narrows on it -- so no cast, and no suppression standing in
        # for one.
        return AcceptOne(rest[0], rest[1], scope)

    if name == "/reject" and len(rest) == 2:
        return DiscardOne(rest[0], rest[1])

    if name == "/help" and not rest:
        return ShowHelp()

    return ShowHelp(f"unrecognized: {line}")


# --- Deciding one proposal at a time -----------------------------------------


@dataclass(frozen=True)
class AcceptThis:
    """Activate the proposal in hand, at this scope."""

    scope: MemoryScope


@dataclass(frozen=True)
class RejectThis:
    """Discard the proposal in hand."""


@dataclass(frozen=True)
class SkipThis:
    """Leave it pending and move to the next one."""


@dataclass(frozen=True)
class StopReview:
    """Leave the walk. Everything not yet decided stays pending."""


@dataclass(frozen=True)
class Unclear:
    """The keystroke means nothing here.

    Deliberately not the same value as :class:`SkipThis`, so a surface can ask
    again instead of advancing. Silently skipping the proposal someone meant to
    accept, because they fumbled one key, is the failure this distinction
    prevents -- and asking again costs nothing, since by definition nothing has
    happened yet.
    """


ReviewDecision = AcceptThis | RejectThis | SkipThis | StopReview | Unclear

REVIEW_CHOICES: dict[str, tuple[str, ReviewDecision]] = {
    "y": ("accept (session)", AcceptThis(SESSION_SCOPE)),
    "u": ("accept (user)", AcceptThis(USER_SCOPE)),
    "n": ("reject", RejectThis()),
    "s": ("skip", SkipThis()),
    "q": ("stop", StopReview()),
}
"""Every key the walk honours, what it is called, and what it means.

One table rather than a parser here and a legend written out somewhere else: the
keys a surface advertises and the keys it accepts are then the same set by
construction. ``_SLASH_HELP`` in the entrypoint is the arrangement that can
drift, and this is deliberately not that.

Accepting appears twice because the scope is the reviewer's choice and never the
model's (the agent's ADR 0021). Giving ``user`` its own key means the wider blast
radius costs a different keystroke, rather than an extra argument that is easy to
leave off and never notice.
"""


def parse_review_key(line: str) -> ReviewDecision:
    """Read one keystroke from someone walking the queue.

    Ambiguity does nothing irreversible. That is the principle
    :func:`bacteria.agent.tools.approval.cli_approve` uses and this reaches the
    opposite key by applying it: there, anything short of an explicit yes denies,
    because a call that does not run costs nothing. Here the destructive answer
    is *reject* -- it throws away something extraction produced and no later turn
    will offer again -- so only an explicit ``n`` does it. An empty line skips,
    which is the ordinary "next" gesture, and everything else is
    :class:`Unclear`.
    """
    choice = line.strip().lower()
    if not choice:
        return SkipThis()
    known = REVIEW_CHOICES.get(choice)
    return known[1] if known else Unclear()
