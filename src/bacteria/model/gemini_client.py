"""Gemini client — a second ModelClient implementation, proving out the
SendsMessages Protocol seam from Part 2. Runtime depends only on the
`.send(messages, **kwargs) -> ModelResponse` shape
(bacteria.runtime.runtime.SendsMessages), never on ModelClient itself, so
this class is a drop-in alternative with zero changes to Runtime.

Reuses the model-layer error taxonomy from bacteria.model.errors — the
asset/serving/contract/credentials split isn't Anthropic-specific, it's
about which part of "talking to a model" failed, so a second provider maps
onto the same categories rather than inventing its own.

Messages/tools travel through Runtime in Anthropic's wire shapes (plain
text content, or {"type": "tool_use"/"tool_result", ...} blocks) because
that's what Runtime and the tool-execution loop actually construct — this
client translates those into Gemini's Content/Part/FunctionDeclaration
shapes on the way in, and translates Gemini's response back into the same
ModelResponse shape on the way out. Verified against the real google-genai
SDK source (github.com/googleapis/python-genai) rather than guessed —
two independent doc pages described a different, non-existent
"interactions" API that turned out to be hallucinated.
"""

from __future__ import annotations

import time
from typing import Any

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from bacteria.model.client import ModelResponse
from bacteria.model.errors import (
    AssetError,
    ContractError,
    CredentialsError,
    ModelLayerError,
    ServingError,
)

_ASSET_HINTS = ("context", "maximum context length", "token", "too long")
_AUTH_HINTS = ("api key", "api_key", "credential", "unauthenticated", "permission")


class GeminiClient:
    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gemini-3.5-flash",
        max_retries: int = 2,
        backoff_seconds: float = 1.0,
    ) -> None:
        # Unlike Anthropic's SDK (lazy — fails on the first send()), a missing
        # key here raises a bare ValueError at construction time. Classify it
        # the same way as every other credentials failure, or this exact
        # failure mode escapes the error taxonomy entirely.
        try:
            self._client = genai.Client(api_key=api_key)
        except ValueError as exc:
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
        id_to_name = self._collect_tool_names(messages)
        contents = [self._to_content(message, id_to_name) for message in messages]

        config_kwargs: dict[str, Any] = {"max_output_tokens": max_tokens}
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
            except Exception as exc:  # noqa: BLE001 — classified below
                classified = self._classify(exc)
                if not isinstance(classified, ServingError):
                    raise classified from exc
                attempt += 1
                if attempt > self.max_retries:
                    raise classified from exc
                time.sleep(self.backoff_seconds * attempt)

    @staticmethod
    def _collect_tool_names(messages: list[dict[str, Any]]) -> dict[str, str]:
        """tool_result blocks only carry tool_use_id, not the tool name Gemini's
        function_response needs — recover it from the tool_use block that
        proposed the call, which Runtime always places earlier in the list."""
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
                parts.append(types.Part.from_function_call(name=block["name"], args=block["input"]))
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
        tool_calls: list[dict[str, Any]] = [
            {"id": f"call_{i}", "name": call.name, "input": dict(call.args or {})}
            for i, call in enumerate(response.function_calls or [])
        ]

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
