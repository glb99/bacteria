from dataclasses import dataclass
from typing import Any, Protocol

from app.agent.tools import ToolCall
from google import genai


@dataclass
class ModelResponse:
    text: str
    tool_calls: list[ToolCall]
    stops_reason: str | None


class SendsToAgent(Protocol):
    async def send(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        system_prompt: str | None = None,
    ) -> ModelResponse: ...
