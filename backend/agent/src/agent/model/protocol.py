"""Import path the runtime already uses.

The protocol types live in :mod:`backend.agent.src.agent.llm.protocol`. This
module keeps that path working so a test can import the runtime.
"""

from backend.agent.src.agent.llm.protocol import ModelResponse, SendsMessages, ToolCall

__all__ = ["ModelResponse", "SendsMessages", "ToolCall"]
