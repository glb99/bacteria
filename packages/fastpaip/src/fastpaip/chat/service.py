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

from bacteria.model.client import ModelClient
from bacteria.model.gemini_client import GeminiClient
from bacteria.model.protocol import SendsMessages
from bacteria.runtime.runtime import RunResult, Runtime
from bacteria.session.protocol import SessionRepository
from bacteria.tools.memory import build_remember_tool
from bacteria.tools.registry import ToolRegistry

PROVIDERS: dict[str, type[SendsMessages]] = {
    "anthropic": ModelClient,
    "gemini": GeminiClient,
}
"""Providers this application can be configured with.

Deliberately a second table rather than a reuse of the agent's own. That one
lives in ``bacteria.interfaces``, which is the agent's composition root for
running standalone, and importing it here would make this application depend on
how the agent's CLI happens to be configured. Two entries duplicated is a
smaller cost than that dependency.
"""


def build_model_client(provider: str) -> SendsMessages:
    """Construct the configured client.

    Raises:
        ValueError: Unrecognized provider. Rejected rather than falling back to a
            default, so a typo cannot quietly bill a different vendor.
    """
    try:
        client_cls = PROVIDERS[provider.strip().lower()]
    except KeyError:
        known = ", ".join(sorted(PROVIDERS))
        raise ValueError(f"unknown model provider {provider!r}; expected one of: {known}") from None
    return client_cls()


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
    repository: SessionRepository, provider: str, session_id: str, user_text: str
) -> RunResult:
    """Advance one turn of a conversation.

    The runtime is constructed per call. It holds no state between turns by
    design — everything that survives is in the repository — so a long-lived one
    would buy nothing but the risk of it acquiring some.
    """
    runtime = Runtime(model_client=build_model_client(provider), session_store=repository)
    return await runtime.run_turn(
        session_id,
        user_text,
        tool_registry=build_registry(repository, session_id),
        approve=_allow,
    )
