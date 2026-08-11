"""Anthropic-backed implementation of :class:`~bacteria.model.protocol.SendsMessages`.

The only module in the package that imports the ``anthropic`` SDK. Everything
else talks to the protocol, so replacing or adding a provider is a change here
and in the CLI's provider table, nowhere else.

Owns two of the three concerns in a model call — choosing the model asset, and
honoring the request/response contract. The third, serving (queueing,
scheduling, batching), is the hosted API's problem and is deliberately not
reimplemented: there is no local queue, no scheduler, and no fallback model.

Invariant: retries re-send a byte-identical request and nothing else. This
module never executes a tool, and cannot — it imports no tool module, no
filesystem, no subprocess. That structural fact, not a comment, is what makes
retrying safe: there is no side effect here for a second attempt to duplicate.
Tool execution lives in :mod:`bacteria.tools.execution`, which calls into this
module and is never called by it.

Not built:
    Prompt caching. Anthropic supports marking stable prefixes as cacheable,
    which would cut cost on long sessions. Unused because sessions are short
    and in-memory. It would go in :meth:`ModelClient.send`, as ``cache_control``
    markers on the system prompt and the older half of ``messages``.

    Streaming. ``send()`` blocks until the full response arrives. A streaming
    variant would need a second protocol method and a runtime that can forward
    partial output, so it is a cross-layer change rather than a local one.
"""

from __future__ import annotations

from typing import Any

import anthropic
import anyio

from bacteria.model.errors import (
    AssetError,
    ContractError,
    CredentialsError,
    ModelLayerError,
    ServingError,
)
from bacteria.model.protocol import ModelResponse, ToolCall

# Anthropic reports "request is too large in some way" as a generic 400. These
# substrings are what separates that from a genuine integration bug, since the
# SDK has no distinct exception type for it.
_ASSET_HINTS = ("context", "maximum context length", "token", "too long")

# Substrings in the SDK's pre-flight TypeError when no credential source at all
# could be resolved. Matched on the message because the SDK raises a plain
# TypeError here rather than anything from its own exception hierarchy.
_AUTH_HINTS = ("authentication", "api_key", "auth_token", "credentials")


class ModelClient:
    """Sends messages to Anthropic and normalizes both replies and failures.

    Args:
        api_key: Falls back to the SDK's own environment lookup when omitted,
            which is the normal path — the CLI loads ``.env`` into the
            environment before constructing this.
        model: Pinned rather than tracking an alias, so an upstream default
            change cannot silently alter behavior.
        max_retries: Additional attempts after the first, for
            :class:`~bacteria.model.errors.ServingError` only.
        backoff_seconds: Multiplied by the attempt number — linear, not
            exponential, because at one concurrent caller there is no thundering
            herd to spread out. Revisit alongside jitter if this ever runs
            behind a surface with many callers.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "claude-sonnet-4-5",
        max_retries: int = 2,
        backoff_seconds: float = 1.0,
    ) -> None:
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self.model = model
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds

    async def send(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        system: str | None = None,
        max_tokens: int = 1024,
    ) -> ModelResponse:
        """Make one model call, retrying only transient serving failures.

        Args:
            messages: Anthropic-shaped message dicts, as built by
                :func:`bacteria.context.assembly.assemble_context` and extended
                by the runtime's tool loop.
            tools: Model-facing schemas from
                :meth:`~bacteria.tools.registry.ToolRegistry.schemas_for_run`.
                These carry no handler and cannot be executed.
            system: System prompt. The runtime uses it to surface memory,
                keeping memory distinguishable from conversation history.
            max_tokens: Response cap. Exceeding it truncates rather than
                failing, so a caller expecting long output must raise it.

        Returns:
            The normalized response. Tool calls in it are proposals.

        Raises:
            ServingError: Transient failure that outlived ``max_retries``.
            AssetError: Request cannot succeed as shaped.
            ContractError: Malformed request, or an unrecognized failure.
            CredentialsError: No usable credentials, or the server rejected them.
        """
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
        }
        if tools:
            kwargs["tools"] = tools
        if system:
            kwargs["system"] = system

        attempt = 0
        while True:
            try:
                # `kwargs` is built once, outside the loop, so every attempt is
                # provably the same request rather than the same by inspection.
                response = await self._client.messages.create(**kwargs)
                # Inside the `try` on purpose: a response whose shape this cannot
                # read is a contract failure like any other, and belongs in the
                # taxonomy rather than escaping as whatever AttributeError or
                # TypeError the parsing happened to raise.
                return self._to_model_response(response)
            except ModelLayerError:
                # Already classified — re-raise rather than classifying twice.
                raise
            except Exception as exc:
                classified = self._classify(exc)
                if not isinstance(classified, ServingError):
                    raise classified from exc
                attempt += 1
                if attempt > self.max_retries:
                    raise classified from exc
                # `anyio.sleep`, not `time.sleep`: the point of this method being
                # a coroutine is that waiting costs no thread, and a blocking
                # sleep in the retry path would give that back at exactly the
                # moment the provider is already struggling.
                await anyio.sleep(self.backoff_seconds * attempt)

    @staticmethod
    def _classify(exc: Exception) -> ModelLayerError:
        """Map a raw SDK exception onto the model-layer taxonomy.

        Ordered most specific first. The final fallback is
        :class:`~bacteria.model.errors.ContractError` because it is the
        non-retrying choice: an unrecognized failure is assumed to be a bug
        here rather than something worth hammering the API over.
        """
        # Raised before any network call, when no credential source resolves.
        # A plain TypeError, so it must be matched on message content — it
        # shares no base class with the anthropic errors checked below.
        if isinstance(exc, TypeError) and any(hint in str(exc).lower() for hint in _AUTH_HINTS):
            return CredentialsError(str(exc))

        # Distinct from the above: the request reached the server and was
        # rejected (401). Same classification, different origin.
        if isinstance(exc, anthropic.AuthenticationError):
            return CredentialsError(str(exc))

        if isinstance(
            exc,
            (
                anthropic.RateLimitError,
                anthropic.APITimeoutError,
                anthropic.APIConnectionError,
                anthropic.InternalServerError,
            ),
        ):
            return ServingError(str(exc))

        if isinstance(exc, anthropic.BadRequestError):
            message = str(exc).lower()
            if any(hint in message for hint in _ASSET_HINTS):
                return AssetError(str(exc))
            return ContractError(str(exc))

        if isinstance(exc, anthropic.APIError):
            return ContractError(str(exc))

        return ContractError(str(exc))

    @staticmethod
    def _to_model_response(response: Any) -> ModelResponse:
        """Flatten Anthropic's content blocks into the protocol's shape.

        Anthropic's block vocabulary is also this project's internal message
        format, so this direction is close to a copy. The Gemini client's
        equivalent method is where the cost of that choice shows up.
        """
        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append({"id": block.id, "name": block.name, "input": block.input})

        return ModelResponse(
            # "" would read as "the model said nothing"; None says "the model
            # produced no text at all", which is the tool-call-only case.
            text="".join(text_parts) or None,
            tool_calls=tool_calls,
            stop_reason=response.stop_reason,
            raw=response,
            # The API's answer, not `self.model`. They usually agree; when they
            # do not, the response is the one telling the truth about what ran.
            model=response.model,
        )
