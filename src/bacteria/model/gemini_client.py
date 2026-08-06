"""Gemini-backed implementation of :class:`~bacteria.model.protocol.SendsMessages`.

Exists to keep the provider seam honest. A protocol with one implementation is
an assertion; with two it is a tested claim. Swapping this in requires no
change to :mod:`bacteria.runtime.runtime`, the tool loop, or the session store
— only the CLI's provider table names it.

This class is also the concrete cost of the decision recorded in
``docs/adr/0006-anthropic-block-shapes-as-internal-format.md``: because the
runtime speaks Anthropic's block vocabulary, a second provider does real
translation work rather than merely matching a method signature. Everything
below the constructor is that translation, in both directions.

Failures are classified into the same
:mod:`~bacteria.model.errors` taxonomy the Anthropic client uses. Those
categories describe which part of "talking to a model" broke, which is not an
Anthropic-specific question, so a provider-specific taxonomy would only make
callers branch on the provider.

Not built:
    Streaming, prompt caching, and the ``thinking`` modes Gemini exposes —
    matching the Anthropic client's scope rather than exceeding it, so that the
    two remain genuinely interchangeable rather than one being a superset.
"""

from __future__ import annotations

import time
from typing import Any

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from bacteria.model.errors import (
    AssetError,
    ContractError,
    CredentialsError,
    ModelLayerError,
    ServingError,
)
from bacteria.model.protocol import ModelResponse, ToolCall

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
        max_retries: Additional attempts, :class:`~bacteria.model.errors.ServingError` only.
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

    def send(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        system: str | None = None,
        max_tokens: int = 1024,
    ) -> ModelResponse:
        """Make one model call, retrying only transient serving failures.

        Accepts the same internal (Anthropic-shaped) arguments as
        :meth:`bacteria.model.client.ModelClient.send` and returns the same
        :class:`~bacteria.model.protocol.ModelResponse`; the translation in
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
        if system:
            config_kwargs["system_instruction"] = system
        if tools:
            config_kwargs["tools"] = [self._to_gemini_tools(tools)]
        config = types.GenerateContentConfig(**config_kwargs)

        attempt = 0
        while True:
            try:
                response = self._client.models.generate_content(
                    model=self.model, contents=contents, config=config
                )
                return self._to_model_response(response)
            except ModelLayerError:
                raise
            except Exception as exc:  # noqa: BLE001 — classified immediately below
                classified = self._classify(exc)
                if not isinstance(classified, ServingError):
                    raise classified from exc
                attempt += 1
                if attempt > self.max_retries:
                    raise classified from exc
                time.sleep(self.backoff_seconds * attempt)

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
    def _to_content(message: dict[str, Any], id_to_name: dict[str, str]) -> types.Content:
        """Translate one internal message into a Gemini ``Content``.

        Three role vocabularies have to be reconciled: the internal format uses
        ``user``/``assistant`` and marks tool results as a ``user`` message
        whose blocks are ``tool_result``, whereas Gemini uses
        ``user``/``model``/``tool`` and infers nothing from part type. Hence the
        ``is_tool_result`` flag rather than a direct role mapping.

        Raises:
            ContractError: Unknown block type. Raised rather than skipped —
                silently dropping a block would send the model a conversation
                that never happened.
        """
        role = message["role"]
        content = message["content"]

        if isinstance(content, str):
            gemini_role = "model" if role == "assistant" else "user"
            return types.Content(role=gemini_role, parts=[types.Part.from_text(text=content)])

        parts: list[types.Part] = []
        is_tool_result = False
        for block in content:
            kind = block["type"]
            if kind == "text":
                parts.append(types.Part.from_text(text=block["text"]))
            elif kind == "tool_use":
                part = types.Part.from_function_call(name=block["name"], args=block["input"])
                # Re-attach the opaque continuation token this same provider
                # emitted on the previous turn. Gemini rejects a function_call
                # part that arrives without it. See _to_model_response.
                signature = (block.get("provider_data") or {}).get("thought_signature")
                if signature is not None:
                    part.thought_signature = signature
                parts.append(part)
            elif kind == "tool_result":
                is_tool_result = True
                name = id_to_name.get(block["tool_use_id"], "unknown_tool")
                parts.append(
                    types.Part.from_function_response(
                        name=name, response={"result": block["content"]}
                    )
                )
            else:
                raise ContractError(f"unsupported content block type: {kind}")

        gemini_role = "tool" if is_tool_result else ("model" if role == "assistant" else "user")
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
        :data:`~bacteria.model.protocol.ToolCall` ``provider_data``, which the
        runtime forwards without reading.
        """
        parts = response.candidates[0].content.parts if response.candidates else []
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
                tool_call["provider_data"] = {"thought_signature": part.thought_signature}
            tool_calls.append(tool_call)

        stop_reason = None
        if response.candidates:
            stop_reason = str(response.candidates[0].finish_reason)

        return ModelResponse(
            text=response.text or None,
            tool_calls=tool_calls,
            stop_reason=stop_reason,
            raw=response,
        )

    @staticmethod
    def _classify(exc: Exception) -> ModelLayerError:
        """Map a raw Gemini SDK exception onto the model-layer taxonomy.

        The SDK splits failures by HTTP range — ``ClientError`` for 4xx,
        ``ServerError`` for 5xx — which does not line up with retryability.
        429 is a 4xx but is exactly the case worth retrying, so it is pulled
        out of the client-error branch explicitly; without that, rate limits
        would fail on the first attempt.
        """
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
