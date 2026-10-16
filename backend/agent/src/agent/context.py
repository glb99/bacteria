from dataclasses import field
from typing import Any

from pydantic.dataclasses import dataclass

from agent.session import SessionState


@dataclass
class AssembledContext:
    messages: list[dict[str, Any]] = field(default_factory=list)
    system_prompt: str | None = None


def assemble_context(
    state: SessionState,
    user_text: str,
    window_size: int = 5
) -> dict[str, Any]:
    """
    Assemble the context for the current session.

    Args:
        state (SessionState): The current state of the session.
        user_text (str): The text input from the user.
        window_size (int): The number of previous messages to include in the context.

    Returns:
        AssembledContext: The assembled context for the session.
    """
    history = [item for item in state.transcript if item.kind == "message"]
    # Not `history[-window_size:]`: a window of 0 makes that the whole list,
    # which turns "show the model nothing from history" into "show it
    # everything" — the exact failure this module exists to prevent, produced by
    # asking for the strictest possible bound.
    recent = history[-window_size:] if window_size > 0 else []
    messages = [{"role": item.payload["role"],
                 "content": item.payload["text"]} for item in recent]
    messages.append({"role": "user", "content": user_text})
    return AssembledContext(
        messages=messages,
    )
