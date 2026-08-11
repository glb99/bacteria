"""The contract every model client implements, and the only one callers use.

This module is the seam between the agent and whichever LLM provider backs it.
Everything upstream of a model client — the runtime, the tool loop, the CLI —
is written against the types declared here and never against a provider SDK.
That is what makes a provider swappable without touching orchestration code,
and it is the reason ``bacteria.model.client`` (Anthropic) and
``bacteria.model.gemini_client`` (Gemini) can be interchanged by the CLI with
no other module noticing.

The contract is deliberately narrow: one method returning one shape. It does
not abstract over streaming, token accounting, prompt caching, or batching. The
rejected alternative was a full provider abstraction layer covering all of
those — written before a second provider exists, such a layer is a guess about
what providers have in common, and the guess generalizes from one SDK's shape.
The second provider then either does not fit or forces the interface wider,
until it is the union of every vendor's surface area and abstracts nothing. A
wide contract has to be re-widened for every provider added; a narrow one only
has to be honored.

Wire-format caveat, and it is a real one: the *messages* passed to
:meth:`SendsMessages.send` are **not** provider-neutral. They use Anthropic's
block shapes (``{"type": "tool_use", ...}`` / ``{"type": "tool_result", ...}``)
because that is what :mod:`bacteria.runtime.runtime` constructs. Any
non-Anthropic client must therefore translate those shapes on the way in and
translate its own response back into :class:`ModelResponse` on the way out —
see :mod:`bacteria.model.gemini_client` for a worked example of how much
translation that actually is. The protocol guarantees the *call* is swappable,
not that the payload crossing it is format-neutral.

A third, neutral format was considered and rejected. It is more principled and
costs more than it looks: another format to design, document, version, and keep
in sync with two moving vendor formats, whose correctness is only observable
through the clients consuming it — so it adds a layer without adding a place to
catch bugs. It would also have been designed by generalizing from a single known
vendor format, which makes "neutral" aspirational. The cost of the choice made
instead is real and falls entirely on non-Anthropic clients; it is paid in
:mod:`bacteria.model.gemini_client`, and it is worth reading that module before
adding a third provider.
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
        model: Which model produced this reply, or ``None`` if the client does
            not report one.

            On the response rather than on the protocol's call surface, and that
            placement is the decision. ADR 0005 keeps ``SendsMessages`` to a
            single method; asking a client which model it holds would widen
            exactly what that ADR protects. It would also answer a different
            question — configuration is an intention, and a client that fell
            back or routed elsewhere would still report the intention. What
            answered is a property of the answer.
    """

    text: str | None
    tool_calls: list[ToolCall]
    stop_reason: str | None
    raw: Any
    model: str | None = None


@runtime_checkable
class SendsMessages(Protocol):
    """What the runtime requires of a model client — the whole of it.

    Structural, not nominal: a class satisfies this by having the method, with
    no base class and no registration. ``@runtime_checkable`` is set so that
    conformance can be asserted directly in tests (``isinstance(client,
    SendsMessages)``) rather than only discovered at call time.

    Note that ``runtime_checkable`` only verifies the method *exists*; it does
    not check the signature — including whether it is a coroutine function. The
    tests that matter for a new provider are the behavioral ones — translation,
    retry classification, tool-call round tripping — not the ``isinstance``
    check.

    ``send`` is a coroutine because it is the system's dominant wait: a turn
    spends seconds inside it, and a synchronous version costs an OS thread for
    every one of those seconds. Implementations must use their SDK's async
    surface rather than wrapping a blocking call, which would move the thread
    cost rather than remove it.
    """

    async def send(self, messages: list[dict[str, Any]], **kwargs: Any) -> ModelResponse: ...
