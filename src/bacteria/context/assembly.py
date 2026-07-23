"""Context assembly — Part 5 (Context, Retrieval, and Memory).

Turns session state (transcript + memory) into a bounded, model-visible
working set for one turn. The runtime decides *when* this runs; this module
decides *what* belongs in the request — the same orchestrator/owner split
established in Part 4.

Strategy is deliberately minimal: a hard recent-message window, not full
compaction/summarization. That's enough to fix "transcript stuffing"
(unbounded growth) without building machinery we don't need yet.

Retrieval (external evidence) is out of scope — no evidence sources exist
yet. When one does, it must stay evidence, not authority (Part 5's boundary):
candidate content the assembled context can include, never something the
runtime trusts by default.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from bacteria.session.store import SessionState

DEFAULT_WINDOW = 20


@dataclass
class AssembledContext:
    messages: list[dict[str, Any]] = field(default_factory=list)
    system: str | None = None


def assemble_context(
    state: SessionState,
    user_text: str,
    window_size: int = DEFAULT_WINDOW,
) -> AssembledContext:
    recent = [item for item in state.transcript if item.kind == "message"][-window_size:]
    messages = [
        {"role": item.payload["role"], "content": item.payload["text"]} for item in recent
    ]
    messages.append({"role": "user", "content": user_text})

    system = _format_memory(state) if state.memory else None
    return AssembledContext(messages=messages, system=system)


def _format_memory(state: SessionState) -> str:
    lines = [f"- {entry.value} (reason: {entry.reason})" for entry in state.memory.values()]
    return "Known context about this user/session:\n" + "\n".join(lines)
