"""Composing the agent for one request, and running a turn with it.

Kept out of ``views.py`` so that the wiring can be exercised without an HTTP
client, and out of ``entrypoints/`` because it is logic rather than
configuration: it decides which provider backs the agent and, more importantly,
what the agent is allowed to do.

Not built:
    Tools. A turn runs with no registry, so the model is offered no capabilities
    and cannot propose any. That is not an oversight — it is the only honest
    setting until approval works here. The agent's approval gate exists to answer
    "should this particular call, with these arguments, run now", and over HTTP
    there is nobody to ask: the request that would answer arrives after the one
    that asked, and the run has already returned. Passing no registry is the one
    option that neither silently approves everything nor pretends to gate.

    What it needs is a pending-approval record, a route that resolves it, and a
    run that can pause and resume — which in turn needs the durable run state the
    agent lists as missing. Adding tools before that would mean choosing between
    a service that acts without consent and one that always refuses; both are
    worse than a service that cannot act at all and says so.
"""

from bacteria.model.client import ModelClient
from bacteria.model.gemini_client import GeminiClient
from bacteria.model.protocol import SendsMessages
from bacteria.runtime.runtime import RunResult, Runtime
from bacteria.session.protocol import SessionRepository

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


async def run_turn(
    repository: SessionRepository, provider: str, session_id: str, user_text: str
) -> RunResult:
    """Advance one turn of a conversation.

    The runtime is constructed per call. It holds no state between turns by
    design — everything that survives is in the repository — so a long-lived one
    would buy nothing but the risk of it acquiring some.
    """
    runtime = Runtime(model_client=build_model_client(provider), session_store=repository)
    return await runtime.run_turn(session_id, user_text)
