"""The contract every model client implements, and the only one callers use.

This module is the seam between the agent and whichever LLM provider backs it.
Everything upstream of a model client — the runtime, the tool loop, the CLI —
is written against the types declared here and never against a provider SDK.
That is what makes a provider swappable without touching orchestration code,
and it is the reason ``bacteria.model.client`` (Anthropic) and
``bacteria.model.gemini_client`` (Gemini) can be interchanged by the CLI with
no other module noticing.

The contract is deliberately narrow: one method returning one shape. It does
not abstract over streaming, token accounting, prompt caching, or batching. A
wide contract has to be re-widened for every provider added; a narrow one only
has to be honored. See ``docs/adr/0005-narrow-model-protocol.md``.

Wire-format caveat, and it is a real one: the *messages* passed to
:meth:`SendsMessages.send` are **not** provider-neutral. They use Anthropic's
block shapes (``{"type": "tool_use", ...}`` / ``{"type": "tool_result", ...}``)
because that is what :mod:`bacteria.runtime.runtime` constructs. Any
non-Anthropic client must therefore translate those shapes on the way in and
translate its own response back into :class:`ModelResponse` on the way out —
see :mod:`bacteria.model.gemini_client` for a worked example of how much
translation that actually is. The protocol guarantees the *call* is swappable,
not that the payload crossing it is format-neutral. See
``docs/adr/0006-anthropic-block-shapes-as-internal-format.md``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, NotRequired, Protocol, TypedDict, runtime_checkable


class ToolCall(TypedDict):
    """A tool invocation the model asked for. Asking is not authority to run.

    A model client's only job with a tool call is to report it. Executing one
    happens in :func:`bacteria.tools.execution.execute_tool_call`, which no
    model client imports — the separation is structural, not conventional.

    Attributes:
        id: Correlates this call with the ``tool_result`` sent back to the
            model afterwards. Providers that do not issue their own ids get a
            synthetic one from the client that produced the call.
        name: Must match a tool registered in a :class:`~bacteria.tools.registry.ToolRegistry`;
            an unregistered name is an error, never a fallback.
        input: Arguments as the model produced them. Untrusted — a schema-valid
            payload is a well-shaped payload, not a correct or safe one.
        provider_data: Opaque provider state that must survive a round trip
            back to that same provider, carried through the runtime unread.
            Gemini's ``thought_signature`` is the motivating case: omit it on
            the follow-up call and the provider rejects the request outright.
            Deliberately not named after any one provider so that a module
            which does not care about it does not have to know it exists.
    """

    id: str
    name: str
    input: dict[str, Any]
    provider_data: NotRequired[dict[str, Any]]


@dataclass
class ModelResponse:
    """One model reply, normalized across providers.

    Attributes:
        text: Concatenated text output, or ``None`` when the model replied
            with tool calls and nothing else.
        tool_calls: Proposals only. Empty when the model asked for no tools.
        stop_reason: Provider-reported reason generation ended. Informational;
            no control flow branches on it today.
        raw: The untouched provider response. An escape hatch for debugging,
            never for control flow — reading it in the runtime would reintroduce
            the provider coupling this module exists to prevent.
    """

    text: str | None
    tool_calls: list[ToolCall]
    stop_reason: str | None
    raw: Any


@runtime_checkable
class SendsMessages(Protocol):
    """What the runtime requires of a model client — the whole of it.

    Structural, not nominal: a class satisfies this by having the method, with
    no base class and no registration. ``@runtime_checkable`` is set so that
    conformance can be asserted directly in tests (``isinstance(client,
    SendsMessages)``) rather than only discovered at call time.

    Note that ``runtime_checkable`` only verifies the method *exists*; it does
    not check the signature. The tests that matter for a new provider are the
    behavioral ones — translation, retry classification, tool-call round
    tripping — not the ``isinstance`` check.
    """

    def send(self, messages: list[dict[str, Any]], **kwargs: Any) -> ModelResponse: ...
