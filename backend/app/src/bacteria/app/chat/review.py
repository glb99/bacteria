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
from typing import Any

from bacteria.agent.session.store import (
    SESSION_SCOPE,
    USER_SCOPE,
    MemoryEntry,
    MemoryScope,
    UnknownSessionError,
)
from bacteria.app.chat.repository import SqlSessionRepository

SCOPES: tuple[MemoryScope, ...] = (SESSION_SCOPE, USER_SCOPE)
"""The scopes a person may activate into, in the order they are offered.

Session first because it is the default and the conservative one: a user-scoped
memory applies to every future conversation that person has, which is the point
of memory and also the wider blast radius (the agent's ADR 0021).
"""


# --- What a review surface is told -------------------------------------------


@dataclass(frozen=True)
class PendingEntry:
    """One suggestion, with what accepting it would cost.

    ``held_by`` names the scopes whose *active* memory already claims this key.
    It is the part of a listing worth computing: proposals are keyed by
    ``(source, key)`` and active memory by ``key`` alone, so accepting a second
    suggestion for a key replaces the first rather than joining it. That collapse
    is deliberate — ADR 0017 puts it at activation, where a human is — and it is
    invisible unless something says so *before* the choice instead of after.
    """

    source: str
    key: str
    value: Any
    reason: str
    held_by: tuple[MemoryScope, ...] = ()


@dataclass(frozen=True)
class Pending:
    """Everything awaiting a decision in one session."""

    entries: tuple[PendingEntry, ...] = ()

    def __len__(self) -> int:
        return len(self.entries)


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


async def pending(repository: SqlSessionRepository, session_id: str) -> Pending | NoSuchSession:
    """What is waiting for a decision, and what each one would replace."""
    try:
        state = await repository.get_state(session_id)
    except UnknownSessionError:
        return NoSuchSession(session_id)

    active = {SESSION_SCOPE: state.memory, USER_SCOPE: state.user_memory}
    return Pending(
        tuple(
            PendingEntry(
                source=source,
                key=key,
                value=entry.value,
                reason=entry.reason,
                held_by=tuple(scope for scope in SCOPES if key in active[scope]),
            )
            for (source, key), entry in sorted(state.proposals.items())
        )
    )


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


ConsoleCommand = SendMessage | ListPending | AcceptOne | DiscardOne | ShowHelp


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
