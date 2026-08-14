"""Composing the agent for one request, and running a turn with it.

Kept out of ``views.py`` so that the wiring can be exercised without an HTTP
client, and out of ``entrypoints/`` because it is logic rather than
configuration: it decides which provider backs the agent and, more importantly,
what the agent is allowed to do.

One tool is registered: ``remember``, which can only *propose* a memory. That is
what makes it registrable at all here. The approval gate exists to answer
"should this call, with these arguments, run now", and over HTTP there is nobody
to ask — the request that would answer arrives after the one that asked. A tool
whose entire effect is "record a suggestion a human will read later" does not
need that question answered, because the human is downstream rather than
upstream. See bacteria's ADR 0017.

Not built:
    Any tool with an effect outside this application. Those still need the
    approval gate to have somebody to ask, which needs a pending-approval
    record, a route that resolves it, and a run that can pause and resume —
    which in turn needs the durable run state the agent lists as missing.
    Registering one now would mean choosing between a service that acts without
    consent and one that always refuses.

    The gate below allows everything, and that is only safe while ``remember``
    is the only tool registered. **Adding a second tool means writing a real
    gate first**, not after.
"""

from bacteria.agent.model.client import ModelClient
from bacteria.agent.model.gemini_client import GeminiClient
from bacteria.agent.model.protocol import SendsMessages
from bacteria.agent.runtime.runtime import RunResult, Runtime
from bacteria.agent.session.protocol import SessionRepository
from bacteria.agent.tools.memory import build_remember_tool
from bacteria.agent.tools.registry import ToolRegistry
from bacteria.app.chat.tasks import extract_memories_task

# Suppressed for the same reason as bacteria's own table: the annotation is the
# contract, and a checker inferring the concrete classes from the literal
# reports the wider declared type as a mismatch.
PROVIDERS: dict[str, type[SendsMessages]] = {  # ty: ignore[invalid-assignment]
    "anthropic": ModelClient,
    "gemini": GeminiClient,
}
"""Providers this application can be configured with.

Deliberately a second table rather than a reuse of the agent's own. That one
lives in ``bacteria.agent.interfaces``, which is the agent's composition root for
running standalone, and importing it here would make this application depend on
how the agent's CLI happens to be configured. Two entries duplicated is a
smaller cost than that dependency.
"""


def build_model_client(provider: str, model: str | None = None) -> SendsMessages:
    """Construct the configured client.

    Args:
        model: Which model the client should use, or ``None`` for the client's
            own default. Present because not every model call in this
            application is a conversation — memory extraction fills a small JSON
            schema and wants the cheapest model a provider offers, while sharing
            the provider and its credential. Passed only when set, so the
            clients' defaults stay the single place a default model is named.

    Raises:
        ValueError: Unrecognized provider. Rejected rather than falling back to a
            default, so a typo cannot quietly bill a different vendor.
    """
    try:
        client_cls = PROVIDERS[provider.strip().lower()]
    except KeyError:
        known = ", ".join(sorted(PROVIDERS))
        raise ValueError(f"unknown model provider {provider!r}; expected one of: {known}") from None
    # Suppressed because `SendsMessages` describes `send` and deliberately says
    # nothing about construction -- the agent's ADR 0005 keeps that protocol to
    # one method, so a checker resolving `client_cls(...)` sees `object.__init__`
    # and no `model` parameter. Both concrete clients take one, with their own
    # defaults, which is why this passes the argument only when it is set.
    # Widening the protocol to describe a constructor would trade a suppression
    # here for the provider abstraction layer that ADR rejects.
    return client_cls(model=model) if model else client_cls()  # ty: ignore[unknown-argument]


def build_registry(repository: SessionRepository, session_id: str) -> ToolRegistry:
    """Build the tools offered for one turn of one session.

    Per turn, not per process, because ``remember`` is bound to the session it
    proposes into. The model supplies the fact; it never supplies the session,
    so it cannot write into a conversation it was not invoked for.
    """
    registry = ToolRegistry()
    registry.register(build_remember_tool(repository, session_id))
    return registry


def _allow(_tool_call) -> bool:
    """Approve every proposed call.

    Correct *only* because the sole registered tool cannot do anything a human
    would want to stop — it records a suggestion that reaches no model until
    someone activates it. This is a statement about the current registry, not a
    policy. See the module docstring before registering anything else.
    """
    return True


async def run_turn(
    repository: SessionRepository,
    provider: str,
    session_id: str,
    user_text: str,
    extract: bool = False,
) -> RunResult:
    """Advance one turn of a conversation.

    The runtime is constructed per call. It holds no state between turns by
    design — everything that survives is in the repository — so a long-lived one
    would buy nothing but the risk of it acquiring some.

    Args:
        extract: Whether to queue memory extraction over what this turn wrote.

            An argument rather than a settings lookup, so configuration stays at
            the edge and a caller can always be read to see what it asked for.

            It lives *here* rather than in the route, and that is the point of
            the parameter existing at all. The enqueue was in
            ``views.take_turn`` first, which made extraction a property of one
            entrance: a second way to run a turn — this repository's admin CLI,
            the planned audio path, a bot — would write a transcript and
            silently never extract from it, with nothing failing and no
            proposals ever appearing. That is the drift
            :mod:`bacteria.app.ingestion.tasks` avoids by having the deferred
            path call the same ``ingest`` the inline one does, and the same
            reasoning applies to a trigger.
    """
    runtime = Runtime(model_client=build_model_client(provider), session_store=repository)
    result = await runtime.run_turn(
        session_id,
        user_text,
        tool_registry=build_registry(repository, session_id),
        approve=_allow,
    )

    if extract:
        # After the turn, so the job sees the transcript this turn wrote rather
        # than the one before it. A turn that raised never reaches here and
        # never enqueues, which loses nothing: the watermark did not move, so
        # the next successful turn extracts from that turn's messages too.
        await extract_memories_task.defer_async(session_id=session_id)

    return result
