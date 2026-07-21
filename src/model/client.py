"""Model client — Part 2 (Foundation Infrastructure, Models, and Inference).

The only module allowed to talk to the Anthropic API directly. Owns the
model asset + interaction contract concerns from Part 2's three-way split;
serving (queueing/scheduling) is left to Anthropic's hosted API, per the
Part 2 decision not to build a custom serving layer.

Retry scope, deliberately narrow: this module retries the literal API call
only, with the exact same request payload, up to `max_retries` times on a
ServingError. It never re-executes anything else. Tool execution (a real
side effect) happens in a different module entirely (planned for Part 6/7)
that calls `send()` — never the other way around — so retrying here can
never accidentally re-run a tool. That module boundary is what makes the
retry logic side-effect-safe, per the Part 2 decision.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import anthropic

from model.errors import AssetError, ContractError, ModelLayerError, ServingError

_ASSET_HINTS = ("context", "maximum context length", "token", "too long")


@dataclass
class ModelResponse:
    text: str | None
    tool_calls: list[dict[str, Any]]
    stop_reason: str | None
    raw: Any


class ModelClient:
    def __init__(
        self,
        api_key: str | None = None,
        model: str = "claude-sonnet-4-5",
        max_retries: int = 2,
        backoff_seconds: float = 1.0,
    ) -> None:
        self._client = anthropic.Anthropic(api_key=api_key)
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
                response = self._client.messages.create(**kwargs)
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
    def _classify(exc: Exception) -> ModelLayerError:
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
        text_parts: list[str] = []
        tool_calls: list[dict[str, Any]] = []
        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append({"id": block.id, "name": block.name, "input": block.input})

        return ModelResponse(
            text="".join(text_parts) or None,
            tool_calls=tool_calls,
            stop_reason=response.stop_reason,
            raw=response,
        )
