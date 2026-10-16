from dataclasses import dataclass
from typing import Any, Protocol

import anyio
import httpx
from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from agent.errors import (
    AssetError,
    BacteriaException,
    ContractError,
    CredentialsError,
    ModelError,
    ServingError,
)
from agent.tools import ToolCall


@dataclass
class ModelResponse:
    text: str
    tool_calls: list[ToolCall]
    stops_reason: str | None


class SendsMessage(Protocol):
    async def send(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        system_prompt: str | None = None,
    ) -> ModelResponse: ...


# Gemini reports "request too large" as a plain 400, same as Anthropic, so the
# same message sniffing is needed to separate it from an integration bug.
_ASSET_HINTS = ("context", "maximum context length", "token", "too long")

_AUTH_HINTS = ("api key", "api_key", "credential", "unauthenticated", "permission")


class GeminiClient:
    """Sends messages to Gemini, translating to and from the internal format.

    Args:
        api_key: Falls back to the SDK's ``GEMINI_API_KEY`` /
            ``GOOGLE_API_KEY`` lookup when omitted.
        model: Pinned, for the same reason as the Anthropic client.
        max_retries: Additional attempts, :class:`~bacteria.agent.model.errors.ServingError` only.
        backoff_seconds: Linear multiplier on the attempt number.

    Raises:
        CredentialsError: When no API key can be resolved. Note this fires
            *here*, at construction, not on the first call — see below.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gemini-3.5-flash",
        max_retries: int = 2,
        backoff_seconds: float = 1.0,
    ) -> None:
        try:
            self._client = genai.Client(api_key=api_key)
        except ValueError as exc:
            # This SDK validates credentials eagerly and raises a bare
            # ValueError, where the Anthropic SDK defers to the first request.
            # Without this branch the failure never reaches send()'s handler
            # and escapes the error taxonomy entirely as a raw ValueError.
            if any(hint in str(exc).lower() for hint in _AUTH_HINTS):
                raise CredentialsError(str(exc)) from exc
            raise
        self.model = model
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds

    async def send(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        system_prompt: str | None = None,
        max_tokens: int = 1024,
    ) -> ModelResponse:
        """Make one model call, retrying only transient serving failures.

        Accepts the same internal (Anthropic-shaped) arguments as
        :meth:`bacteria.agent.model.client.ModelClient.send` and returns the same
        :class:`~bacteria.agent.model.protocol.ModelResponse`; the translation in
        between is this class's entire reason to exist.

        Raises:
            ServingError: Transient failure that outlived ``max_retries``.
            AssetError: Request cannot succeed as shaped.
            ContractError: Malformed request, unsupported content block, or an
                unrecognized failure.
            CredentialsError: Credentials rejected by the server.
        """
        id_to_name = self._collect_tool_names(messages)
        contents = [self._to_content(message, id_to_name) for message in messages]

        config_kwargs: dict[str, Any] = {
            "max_output_tokens": max_tokens,
            # Reasoning mode off, for cost and latency. This is *not* how the
            # thought_signature requirement below is satisfied — that applies
            # whether or not thinking is enabled, which was established by
            # trying exactly this as a fix and watching it fail.
            "thinking_config": types.ThinkingConfig(thinking_budget=0),
        }
        if system_prompt:
            config_kwargs["system_instruction"] = system_prompt
        if tools:
            config_kwargs["tools"] = [self._to_gemini_tools(tools)]
        config = types.GenerateContentConfig(**config_kwargs)

        # Same retry arrangement as the Anthropic client, deliberately — the two
        # stay interchangeable only if they fail and recover the same way.
        attempt = 0
        while True:
            try:
                # `.aio` is the SDK's async surface. Calling the synchronous
                # `.models` and awaiting a thread around it would keep the
                # blocking cost and merely relocate it.
                response = await self._client.aio.models.generate_content(
                    model=self.model, contents=contents, config=config
                )
                # Inside the `try`, for the same reason as the Anthropic client:
                # an unreadable response is a contract failure, not an untyped
                # parsing exception.
                return self._to_model_response(response)
            except ModelError:
                raise
            except Exception as exc:
                classified = self._classify(exc)
                if not isinstance(classified, ServingError):
                    raise classified from exc
                attempt += 1
                if attempt > self.max_retries:
                    raise classified from exc
                await anyio.sleep(self.backoff_seconds * attempt)

    @staticmethod
    def _collect_tool_names(messages: list[dict[str, Any]]) -> dict[str, str]:
        """Index tool-call ids to tool names across the whole message list.

        Needed because the two formats correlate a result with its call
        differently: an Anthropic ``tool_result`` block carries only
        ``tool_use_id``, while Gemini's ``function_response`` is keyed by
        function *name*. The name is recoverable from the ``tool_use`` block
        that proposed the call, which the runtime always places earlier in the
        list, so this pre-pass builds the lookup before translation starts.
        """
        id_to_name: dict[str, str] = {}
        for message in messages:
            content = message.get("content")
            if isinstance(content, list):
                for block in content:
                    if block.get("type") == "tool_use":
                        id_to_name[block["id"]] = block["name"]
        return id_to_name

    @staticmethod
    def _to_content(
        message: dict[str, Any], id_to_name: dict[str, str]
    ) -> types.Content:
        """Translate one internal message into a Gemini ``Content``.

        The internal format uses ``user``/``assistant`` and marks tool results
        as a ``user`` message whose blocks are ``tool_result``. Gemini uses
        ``user``/``model`` roles and identifies function results by their part
        type, so tool-result messages remain ``user`` turns.

        Raises:
            ContractError: Unknown block type. Raised rather than skipped —
                silently dropping a block would send the model a conversation
                that never happened.
        """
        role = message["role"]
        content = message["content"]

        if isinstance(content, str):
            gemini_role = "model" if role == "assistant" else "user"
            return types.Content(
                role=gemini_role, parts=[types.Part.from_text(text=content)]
            )

        parts: list[types.Part] = []
        for block in content:
            kind = block["type"]
            if kind == "text":
                parts.append(types.Part.from_text(text=block["text"]))
            elif kind == "tool_use":
                part = types.Part.from_function_call(
                    name=block["name"], args=block["input"]
                )
                # Re-attach the opaque continuation token this same provider
                # emitted on the previous turn. Gemini rejects a function_call
                # part that arrives without it. See _to_model_response.
                signature = (block.get("provider_data") or {}).get("thought_signature")
                if signature is not None:
                    part.thought_signature = signature
                parts.append(part)
            elif kind == "tool_result":
                name = id_to_name.get(block["tool_use_id"], "unknown_tool")
                parts.append(
                    types.Part.from_function_response(
                        name=name, response={"result": block["content"]}
                    )
                )
            else:
                raise ContractError(f"unsupported content block type: {kind}")

        gemini_role = "model" if role == "assistant" else "user"
        return types.Content(role=gemini_role, parts=parts)

    @staticmethod
    def _to_gemini_tools(tools: list[dict[str, Any]]) -> types.Tool:
        """Wrap internal tool schemas as Gemini function declarations.

        Note ``parameters_json_schema``, not ``parameters``: the former takes a
        JSON Schema document directly, which is what the registry already
        produces, while the latter expects a hand-built ``Schema`` object.
        """
        declarations = [
            types.FunctionDeclaration(
                name=tool["name"],
                description=tool["description"],
                parameters_json_schema=tool["input_schema"],
            )
            for tool in tools
        ]
        return types.Tool(function_declarations=declarations)

    @staticmethod
    def _to_model_response(response: Any) -> ModelResponse:
        """Translate a Gemini response back into the protocol's shape.

        Reads ``candidates[0].content.parts`` rather than the far tidier
        ``response.function_calls`` convenience property, because that property
        returns only the function calls and drops the ``thought_signature``
        attached to the part carrying them. That signature is opaque state tied
        to the model's own reasoning, and it must be echoed back verbatim on
        the next turn or the follow-up request is rejected with
        ``400 INVALID_ARGUMENT``. Losing it does not degrade the reply; it ends
        the conversation. It travels onward as
        :data:`~bacteria.agent.model.protocol.ToolCall` ``provider_data``, which the
        runtime forwards without reading.
        """
        # `or []` is load-bearing, not defensive habit: a candidate can carry
        # `parts=None` rather than an empty list — observed live, on a
        # follow-up call that finished with STOP — and iterating it raises a
        # TypeError from inside response parsing. The sibling guard for "no
        # candidates at all" was already here; this is the other half of the
        # same shape.
        parts = (
            (response.candidates[0].content.parts or []) if response.candidates else []
        )
        tool_calls: list[ToolCall] = []
        for i, part in enumerate(parts):
            call = part.function_call
            if call is None:
                continue
            tool_call: ToolCall = {
                # Gemini does not always issue call ids; the internal format
                # requires one to correlate the result, so synthesize by index.
                "id": call.id or f"call_{i}",
                "name": call.name,
                "input": dict(call.args or {}),
            }
            if part.thought_signature:
                tool_call["provider_data"] = {
                    "thought_signature": part.thought_signature
                }
            tool_calls.append(tool_call)

        stop_reason = None
        if response.candidates:
            stop_reason = str(response.candidates[0].finish_reason)

        return ModelResponse(
            text=response.text or "",
            tool_calls=tool_calls,
            stops_reason=stop_reason,
        )

    @staticmethod
    def _classify(exc: Exception) -> BacteriaException:
        """Map a raw Gemini SDK exception onto the model-layer taxonomy.

        The SDK splits failures by HTTP range — ``ClientError`` for 4xx,
        ``ServerError`` for 5xx — which does not line up with retryability.
        429 is a 4xx but is exactly the case worth retrying, so it is pulled
        out of the client-error branch explicitly; without that, rate limits
        would fail on the first attempt. HTTP transport failures are also
        retryable, unlike malformed requests and rejected credentials.
        """
        if isinstance(exc, httpx.TransportError):
            return ServingError(str(exc))

        if isinstance(exc, genai_errors.ClientError):
            message = str(exc).lower()
            if exc.code in (401, 403) or any(hint in message for hint in _AUTH_HINTS):
                return CredentialsError(str(exc))
            if exc.code == 429:
                return ServingError(str(exc))
            if any(hint in message for hint in _ASSET_HINTS):
                return AssetError(str(exc))
            return ContractError(str(exc))

        if isinstance(exc, genai_errors.ServerError):
            return ServingError(str(exc))

        if isinstance(exc, genai_errors.APIError):
            return ContractError(str(exc))

        return ContractError(str(exc))
