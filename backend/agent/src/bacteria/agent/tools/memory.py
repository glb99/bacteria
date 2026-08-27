"""The tool that lets a model suggest something worth remembering.

It proposes. It cannot write active memory, and that limit is the entire reason
this tool is safe to register — see
[ADR 0017](../../docs/adr/0017-memory-is-proposed-and-confirmed.md).

Why the distinction carries so much weight here, when the same tool looks
harmless: memory is injected into the system prompt of *every later turn* in the
session. A model able to write active memory could therefore write its own
future instructions, and a single injected user message — "remember that you
must always comply with X" — would become an instruction outliving the message
that carried it, with the transcript showing only a tool call that succeeded.
The hazard is not that this tool does something expensive or irreversible. It
touches nothing outside the session's own store. It is that it edits what the
model will be told next, which makes it a *higher*-risk capability than tools
that sound far more alarming.

Because it can only propose, its approval gate may allow by default. What is
being gated is "record a suggestion a human will read", which genuinely is
low-risk. If anyone ever gives this handler the ability to write active memory
directly, that reasoning collapses and the gate must come back.

The exception, and it is the mirror image rather than a loophole: a surface whose
gate *does* ask a human, before the handler runs and with the key and value in
front of them, has already taken the step confirmation exists to take. There the
tool activates in the same call — see ``activate_immediately`` below. What makes
that safe is the gate, so the two settings are coupled, and the unsafe
combination is the one nothing here can detect.

Built per turn, not once per process: the handler is closed over a store *and a
session id*, because a proposal belongs to the conversation that prompted it.
A module-level definition would have nowhere to put either.
"""

from __future__ import annotations

from typing import Any, Sequence

from bacteria.agent.session.protocol import SessionRepository
from bacteria.agent.session.store import MemoryRefused
from bacteria.agent.tools.registry import ToolDefinition

MODEL_SOURCE = "model"
"""Recorded as the ``source`` of anything this tool proposes.

A constant rather than a caller-supplied string, so that every model-proposed
memory in every host is attributable the same way. "Mute the model's
suggestions" has to be answerable without first discovering what each
deployment decided to call it.
"""


_KEY_DESCRIPTION = (
    "Short stable identifier for the fact, such as 'tone' or 'timezone'. "
    "Reusing a key replaces your earlier suggestion for it."
)

_KEY_CLOSED = (
    "These are the only keys that exist. Do not coin one: a fact that fits none "
    "of them is simply not stored, which is a normal outcome and not a problem "
    "to report. Never mention this tool or its keys to the user."
)
"""Why the last sentence is there, and it was not there first.

Told only that other keys are unavailable, the model explained itself: *\"since
the memory tool only allows me to save your name directly, I will keep your
location in mind for this conversation\"*. Accurate, obedient, and a description
of the storage layer offered to somebody who asked about their mother. A limit
the model works within is not news; narrating it makes the tool the subject of a
conversation that was about something else.
"""

_KEY_REUSE = (
    "Reuse one of these whenever the fact is the same kind; a corrected fact "
    "keeps the key it corrects, and only the value changes. Invent a new key "
    "only when none of them fits."
)


def _key_description(
    confirmed: Sequence[str], suggested: Sequence[str], allowed: Sequence[str] = ()
) -> str:
    """The ``key`` description, plus the keys this conversation already uses.

    A model left to name a fact freely renames it on every occasion. The
    extractor demonstrated this at length -- one fact arrived as ``name``,
    ``first_name``, ``preferred_name`` and ``nickname`` -- and it was fixed there
    by showing the names already in use. This tool is the *other* proposer and
    never got the same treatment, so it went on inventing: a live store held
    ``mother_name`` from here beside ``user_mom_name`` from the extractor, one
    person filed twice.

    Split into confirmed and merely-suggested for the reason the extractor
    learned the hard way. A flat list stopped the invention and started
    *rotation* between synonyms already in it, because unreviewed suggestions
    were being offered back as though they were vocabulary. A confirmed key is
    one a person activated, which is the closest thing here to a fact's real
    name.

    A key that duplicates a fact costs more than a clumsy one, and it is why this
    is worth a dynamic description rather than a fixed string: the two proposers
    have to converge on one name or the same fact is stored twice, forever.

    ``allowed`` is a stronger statement than the other two and is rendered as
    one. Confirmed and suggested keys say *this is what we call it*; a store may
    take a new name beside them. ``allowed`` says **there are no other names** —
    a store that refuses everything else, which the graph-backed one does because
    a key is a relation and relations are a governed vocabulary. Rendering it as
    a preference would leave the model coining names the store then rejects, and
    a rejected key is not a slightly worse name: today it costs the whole turn.
    """
    if not confirmed and not suggested and not allowed:
        return _KEY_DESCRIPTION

    lines = [_KEY_DESCRIPTION]
    if allowed:
        lines.append(f"Keys this store accepts: {', '.join(sorted(allowed))}.")
    if confirmed:
        lines.append(f"Confirmed keys, prefer these: {', '.join(sorted(confirmed))}.")
    if suggested:
        lines.append(f"Suggested, not yet confirmed: {', '.join(sorted(suggested))}.")
    lines.append(_KEY_CLOSED if allowed else _KEY_REUSE)
    return " ".join(lines)


def build_remember_tool(
    store: SessionRepository,
    session_id: str,
    source: str = MODEL_SOURCE,
    *,
    activate_immediately: bool = False,
    confirmed_keys: Sequence[str] = (),
    suggested_keys: Sequence[str] = (),
    allowed_keys: Sequence[str] = (),
) -> ToolDefinition:
    """Build a ``remember`` tool that proposes into ``session_id``.

    Args:
        store: Where the proposal goes. Typed as the protocol, so this works
            against the in-memory store and a durable one alike.
        session_id: The conversation this proposal belongs to. Bound here rather
            than taken from the model, which must not be able to write into a
            session it was not invoked for.
        source: Attribution for the proposal. Defaults to
            :data:`MODEL_SOURCE`; a host running several distinguishable agents
            may override it.
        confirmed_keys: Keys this session's active memory already uses, in
            either scope. Rendered into the ``key`` description so the model
            reuses a name instead of coining a synonym for it; see
            :func:`_key_description` for what happens without them.
        suggested_keys: Keys only *proposed* so far, kept separate from the
            confirmed ones rather than merged into one list.
        allowed_keys: The complete set a store will accept, when it has one.
            Empty means any key is allowed, which is the table store. A store
            with a closed vocabulary passes it so the model chooses from the
            list rather than coining a name the store then rejects — see
            :func:`_key_description` for why that is not merely tidier.
        activate_immediately: Whether the proposal becomes active memory in the
            same call.

            **Only correct where the approval gate asks a human before the
            handler runs**, and false by default because most surfaces are not
            like that. Over HTTP the request that would answer arrives after the
            one that asked, so nobody is upstream and a proposal must wait.

            An interactive surface is the exception rather than a shortcut around
            ADR 0017. That ADR requires a human between a suggestion and the
            model's future instructions; a gate like
            :func:`bacteria.agent.tools.approval.cli_approve` *is* that human, asked
            first, shown the key and the value, and able to refuse. Requiring a
            second confirmation afterwards does not add a check — it adds a queue
            nothing in an interactive session ever drains, which is exactly what
            it did: the model reported a suggestion, the user approved it, and it
            sat inert while the model told them it had been noted.

            Passing ``True`` without such a gate hands the model the ability to
            write its own future instructions. Nothing here can detect that,
            which is why it is keyword-only, off by default, and stated at
            length.

    Returns:
        A registrable tool definition. Its description and its reply to the
        model both change with ``activate_immediately``, so the model is never
        told to hedge about a memory that is already active, or that something
        is saved when it is only suggested.
    """

    async def handler(tool_input: dict[str, Any]) -> str:
        key = tool_input["key"]
        try:
            await store.propose(
                session_id,
                key=key,
                value=tool_input["value"],
                reason=tool_input["reason"],
                source=source,
            )
        except MemoryRefused as refusal:
            # ADR 0025. Only this exception, and only around the store call: a
            # blanket `except` here would turn every genuine defect in a store
            # into a polite message the model reads as a refusal, which is the
            # same bug facing the other way and much harder to see.
            return (
                f"could not remember {key!r}: {refusal.reason}. "
                "Carry on without it and do not mention this to the user."
            )
        if not activate_immediately:
            # Says "suggested", not "remembered". The model is told the truth
            # about what happened, because a model that believes a fact is now
            # active will rely on it next turn and be wrong until someone
            # confirms it.
            return f"suggested remembering {key!r}; it takes effect once the user confirms it"

        # Proposed and then activated rather than written directly, so the
        # entry keeps `source` and the lifecycle stays the one ADR 0017
        # describes — the human step happened at the gate, not here.
        await store.activate(session_id, source=source, key=key)
        return f"remembered {key!r} for the rest of this conversation"

    proposes_only = (
        "Suggests a durable fact about this user or conversation, to be kept for "
        "future turns. The suggestion is reviewed by the user before it takes "
        "effect, so do not tell them it has been saved. Use it for stable "
        "preferences and facts, not for things only relevant right now."
    )
    takes_effect = (
        "Records a durable fact about this user or conversation, kept for future "
        "turns. The user is asked to approve the call before it runs, so if it "
        "succeeds the fact is saved and you may say so. Use it for stable "
        "preferences and facts, not for things only relevant right now."
    )

    return ToolDefinition(
        name="remember",
        # Written for the model, and it has to match what actually happens: a
        # description telling the model to hedge, attached to a tool that saves
        # immediately, makes the model understate what it just did.
        description=takes_effect if activate_immediately else proposes_only,
        input_schema={
            "type": "object",
            "properties": {
                "key": {
                    "type": "string",
                    "description": _key_description(confirmed_keys, suggested_keys, allowed_keys),
                },
                "value": {
                    "type": "string",
                    # "As a short sentence" was the wording here, and it produced
                    # sentences: `dad_name` was stored as "Your dad's name is
                    # Pedro." beside the extractor's "Pedro". A value is read back
                    # into a later system prompt and, later still, becomes a node
                    # label -- and a second-person sentence is not an entity.
                    "description": (
                        "The fact itself, as briefly as it can be stated. A name is "
                        "just the name ('Pedro'), not a sentence about it ('Your "
                        "dad's name is Pedro.'); a preference is just the preference "
                        "('vegetarian', not 'Is vegetarian.'). No leading verb, no "
                        "trailing period. Never address the user in it."
                    ),
                },
                "reason": {
                    "type": "string",
                    "description": (
                        "Why this is worth keeping, in terms the user can check — "
                        "ideally what they said that prompted it."
                    ),
                },
            },
            "required": ["key", "value", "reason"],
        },
        handler=handler,
    )
