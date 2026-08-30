"""Constructing the configured model client.

Infrastructure, and here for the same reason ``db.py`` is: it resolves a
settings string to a thing that talks to a vendor, exactly as ``get_engine``
resolves one to an engine. It names no domain concept, declares no table and
mounts no route, so ``core/`` is allowed to hold it — and this codebase's own
boundary check is what decides that rather than taste.

It lived in the personal domain's service until the architecture agent imported
it, which is the moment a provider factory stopped being one domain's business.
That import was the last edge from the second domain into the first.

**Not the agent's own table.** ``bacteria.agent.interfaces`` has one, and it is
the agent's composition root for running standalone; importing it would make
this application depend on how the agent's CLI happens to be configured. Two
entries duplicated is a smaller cost than that dependency — the argument the
table below was written with, unchanged by the move.
"""

from bacteria.agent.model.client import ModelClient
from bacteria.agent.model.gemini_client import GeminiClient
from bacteria.agent.model.protocol import SendsMessages

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
