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

Memory is bounded too, and by the same reasoning as the message window. It was
briefly not: every entry was rendered, so the one channel the window did not
watch was the one that could overflow it. The bound is on the read side, most
recent first, so it is describable the same way — "the twenty most recent
memories" is something a user can be told.

Not built:
    Retrieval over external evidence. There is no external source — no
    documents, no search, no vector store — so there is nothing to retrieve.
    When one exists, it plugs in here as an *additional section*, and it must
    arrive as candidate evidence rather than authority: assembled context is a
    claim about what is relevant, and a retrieved passage carries no more weight
    than the retriever's confidence in it.

    Relevance ranking over memory. Distinct from the above, and easy to conflate
    with it: this one adds no section, it replaces how :func:`_format_memory`
    chooses. Memory is selected by recency today, so a session's twentieth most
    recent fact is invisible on the turn it finally matters. Ranking the entries
    against the incoming message instead is what would make this semantic memory
    by mechanism and not only by role — see the note in
    :mod:`bacteria.session.store`. Nothing structural is in the way: this
    function already receives ``user_text``, which is the query, and uses it
    only to append the new message.

    The reason it is not built is a tension rather than a missing dependency.
    Ranking makes a memory's absence *silent and query-dependent* — the same
    turn, phrased differently, surfaces a different set, and a fact the owner
    deliberately preserved can vanish with nothing reporting it. That is the
    failure `ADR 0010` rejected when it declined summarization, and rejecting it
    for messages while accepting it for memory would be inconsistent: a memory
    was kept on purpose, so losing one silently is worse than losing an old
    message. Recency is blunter and fails predictably, which is the same trade
    the message window makes. Whoever builds this has to answer what happens to
    a preserved fact that did not score well, and "it was not relevant" is not
    an answer the owner who wrote it can check.

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

DEFAULT_MEMORY_LIMIT = 20
"""Memory entries surfaced in the system prompt, most recent first.

Matches the message window rather than being tuned separately, because the two
compete for the same budget and one number is easier to reason about than two.

Dropping a memory is a worse loss than dropping an old message — it was kept
deliberately, where the message merely happened — which argues for a higher
limit, not for no limit. Unbounded was the previous behaviour and is the one
outcome that is certainly wrong: memory would grow until it displaced the
conversation entirely, and nothing would report it.
"""


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
    memory_limit: int = DEFAULT_MEMORY_LIMIT,
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
        memory_limit: How many memory entries to surface, most recent first.

    Returns:
        The assembled context. Total message count is at most
        ``window_size + 1``.
    """
    history = [item for item in state.transcript if item.kind == "message"]
    # Not `history[-window_size:]`: a window of 0 makes that the whole list,
    # which turns "show the model nothing from history" into "show it
    # everything" — the exact failure this module exists to prevent, produced by
    # asking for the strictest possible bound.
    recent = history[-window_size:] if window_size > 0 else []
    messages = [
        {"role": item.payload["role"], "content": item.payload["text"]} for item in recent
    ]
    messages.append({"role": "user", "content": user_text})

    # `or None` so that a limit of 0 yields no system prompt rather than an
    # empty one, which some providers reject outright.
    system = _format_memory(state, memory_limit) or None if state.memory else None
    return AssembledContext(messages=messages, system=system)


def _format_memory(state: SessionState, limit: int) -> str:
    """Render the most recent memory entries as a system prompt.

    Each line carries its ``reason`` alongside its value. That is provenance
    for the model as much as for us: a fact plus why it was kept is something
    the model can weigh, where a bare assertion can only be obeyed.

    Sorted ascending and trimmed from the front, rather than sorted descending
    and reversed. The two differ on ties: Python's sort is stable, so ascending
    keeps entries that share a timestamp in insertion order, where reversing a
    descending sort would flip them. Several memories written in one request do
    share a timestamp, so this is the ordinary case, not a corner one — and an
    order that changes between turns is an unnecessary difference in the prompt.
    """
    if limit <= 0:
        return ""
    oldest_first = sorted(state.memory.values(), key=lambda entry: entry.created_at)
    lines = [f"- {e.value} (reason: {e.reason})" for e in oldest_first[-limit:]]
    return "Known context about this user/session:\n" + "\n".join(lines)
