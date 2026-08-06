"""Decides what the model is allowed to see on a given turn.

The transcript is the record of everything that happened. The context is the
much smaller working set chosen for one request. Conflating them is the default
failure of a naive agent: append every turn to a list, send the list, and watch
cost, latency, and distraction grow without bound until the window overflows
and the whole conversation breaks at once.

Ownership split with the runtime: the runtime decides *when* context is
assembled, this module decides *what* goes in it. The runtime never reads the
transcript directly, which keeps the "what is in context" question answerable
by reading one function instead of auditing the orchestration path.

The current strategy is a hard recent-message window — the last N messages,
nothing older. Blunt on purpose. It fixes unbounded growth, which is the
failure that actually happens, without the machinery of summarization. That was
the rejected alternative, and it trades one failure for a worse-behaved one: a
summarizer decides what to discard, silently, and when it discards the wrong
thing the model behaves as though something never happened. Running out of
window is at least loud. Losing the start of a long conversation is the accepted
cost here, and it is accepted because it is *comprehensible* — "we keep the last
twenty messages" is something a user can be told.

Memory is surfaced through ``system``, never appended to ``messages``. Merged
into the message list it would be indistinguishable from something the user
actually said, and the model would treat a preference the system chose to
preserve as a statement someone made this turn.

Not built:
    Retrieval. There is no external evidence source — no documents, no search,
    no database — so there is nothing to retrieve. When one exists, it plugs in
    here as an additional section, and it must arrive as *candidate evidence*
    rather than authority: assembled context is a claim about what is relevant,
    and a retrieved passage carries no more weight than the retriever's
    confidence in it.

    Summarization and compaction. Would replace the window with
    summary-of-old-turns plus recent turns. Needed once conversations
    routinely exceed the window; a summarizer must then answer for what it
    dropped, which is why it is not built speculatively.

    Token-aware budgeting. The window counts *messages*, not tokens, so twenty
    long messages cost far more than twenty short ones. A real budget would
    measure tokens and trim to fit, which requires a tokenizer per provider.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from bacteria.session.store import SessionState

DEFAULT_WINDOW = 20
"""Messages kept from history. Small enough to stay cheap, large enough that a
normal back-and-forth does not lose its own thread mid-conversation."""


@dataclass
class AssembledContext:
    """One turn's model-visible working set.

    Attributes:
        messages: Conversation history plus the new user message, in the
            internal (Anthropic-shaped) format.
        system: System prompt, or ``None`` when there is nothing to say. Carries
            memory, kept out of ``messages`` deliberately.
    """

    messages: list[dict[str, Any]] = field(default_factory=list)
    system: str | None = None


def assemble_context(
    state: SessionState,
    user_text: str,
    window_size: int = DEFAULT_WINDOW,
) -> AssembledContext:
    """Build the working set for one turn.

    Only ``message`` transcript items become messages. Tool-call records are
    filtered out: they exist so a human or an audit can reconstruct what ran,
    and replaying them as conversation would show the model a garbled second
    version of an exchange it already saw in its own tool-result blocks.

    Args:
        state: Session state, as returned by
            :meth:`~bacteria.session.store.SessionStore.get_state`. Read-only
            here; assembling context never writes.
        user_text: The new message, always included regardless of ``window_size``
            — dropping the thing being responded to would be incoherent.
        window_size: How many prior messages to keep.

    Returns:
        The assembled context. Total message count is at most
        ``window_size + 1``.
    """
    recent = [item for item in state.transcript if item.kind == "message"][-window_size:]
    messages = [
        {"role": item.payload["role"], "content": item.payload["text"]} for item in recent
    ]
    messages.append({"role": "user", "content": user_text})

    system = _format_memory(state) if state.memory else None
    return AssembledContext(messages=messages, system=system)


def _format_memory(state: SessionState) -> str:
    """Render memory entries as a system prompt.

    Each line carries its ``reason`` alongside its value. That is provenance
    for the model as much as for us: a fact plus why it was kept is something
    the model can weigh, where a bare assertion can only be obeyed.
    """
    lines = [f"- {entry.value} (reason: {entry.reason})" for entry in state.memory.values()]
    return "Known context about this user/session:\n" + "\n".join(lines)
