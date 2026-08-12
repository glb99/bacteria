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

from typing import Any

from bacteria.agent.session.protocol import SessionRepository
from bacteria.agent.tools.registry import ToolDefinition

MODEL_SOURCE = "model"
"""Recorded as the ``source`` of anything this tool proposes.

A constant rather than a caller-supplied string, so that every model-proposed
memory in every host is attributable the same way. "Mute the model's
suggestions" has to be answerable without first discovering what each
deployment decided to call it.
"""


def build_remember_tool(
    store: SessionRepository,
    session_id: str,
    source: str = MODEL_SOURCE,
    *,
    activate_immediately: bool = False,
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
        await store.propose(
            session_id,
            key=key,
            value=tool_input["value"],
            reason=tool_input["reason"],
            source=source,
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
                    "description": (
                        "Short stable identifier for the fact, such as 'tone' or "
                        "'timezone'. Reusing a key replaces your earlier suggestion "
                        "for it."
                    ),
                },
                "value": {
                    "type": "string",
                    "description": "The fact itself, as a short sentence.",
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
