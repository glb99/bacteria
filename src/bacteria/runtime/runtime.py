"""Runtime — Part 4 (Runtimes, Workflows, and Durable Execution).

Owns turn-level sequencing: generates a lightweight run identity, orchestrates
calls into the model client and session store, and enforces step-boundary
discipline around side effects so a step is never blindly re-executed.

In-memory only — no persistence, no replay/resume-after-crash. That's a
deliberate scope decision (see docs/SYSTEM_DESIGN.md, Part 4), not an
oversight: a run's identity and step history live only for the duration of
one turn and are discarded afterward.

Context assembly (what messages actually get sent to the model) is owned by
bacteria.context.assembly, not by the runtime — Part 5's decision, following
the same orchestrator/owner split the runtime already keeps with the model
client and session store.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Callable, Protocol

from bacteria.context.assembly import assemble_context
from bacteria.model.client import ModelResponse
from bacteria.session.store import SessionState, SessionStore, TranscriptItem
from bacteria.tools.execution import ToolResult, execute_tool_call
from bacteria.tools.registry import ToolRegistry


class StepAlreadyExecutedError(Exception):
    """A step was about to run again after already completing once this run."""


class StepTracker:
    """Tracks which steps (side effects) have already executed within one run.

    This is the run-level counterpart to the side-effect-aware retry logic in
    src/model/client.py: it doesn't provide durability, but it guarantees a
    step can't be silently re-executed within a single in-memory run.
    """

    def __init__(self) -> None:
        self._executed: set[str] = set()

    def has_run(self, step_id: str) -> bool:
        return step_id in self._executed

    def run_once(self, step_id: str, fn: Callable[[], Any]) -> Any:
        if self.has_run(step_id):
            raise StepAlreadyExecutedError(step_id)
        result = fn()
        self._executed.add(step_id)
        return result


class SendsMessages(Protocol):
    def send(self, messages: list[dict[str, Any]], **kwargs: Any) -> ModelResponse: ...


@dataclass
class RunResult:
    run_id: str
    response: ModelResponse
    committed_state: SessionState


class Runtime:
    """Orchestrates one turn. Owns sequencing only — the model client owns
    model-call logic, the session store owns state ownership. The runtime
    does not reimplement either."""

    def __init__(self, model_client: SendsMessages, session_store: SessionStore) -> None:
        self._model_client = model_client
        self._session_store = session_store

    def run_turn(
        self,
        session_id: str,
        user_text: str,
        tool_registry: ToolRegistry | None = None,
    ) -> RunResult:
        run_id = str(uuid.uuid4())
        step_tracker = StepTracker()

        state = self._session_store.get_state(session_id)
        context = assemble_context(state, user_text)
        tools = tool_registry.schemas_for_run() if tool_registry else None

        response: ModelResponse = step_tracker.run_once(
            f"{run_id}:model_call",
            lambda: self._model_client.send(
                messages=context.messages, system=context.system, tools=tools
            ),
        )

        transcript_items = [TranscriptItem(kind="message", payload={"role": "user", "text": user_text})]

        if response.tool_calls and tool_registry is not None:
            results: list[ToolResult] = [
                step_tracker.run_once(
                    f"{run_id}:tool_call:{call['id']}",
                    lambda call=call: execute_tool_call(call, tool_registry),
                )
                for call in response.tool_calls
            ]
            transcript_items.extend(
                TranscriptItem(
                    kind="tool_call",
                    payload={"name": result.name, "output": result.output},
                )
                for result in results
            )

            follow_up_messages = context.messages + [
                {"role": "assistant", "content": self._assistant_content_blocks(response)},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": result.tool_call_id,
                            "content": str(result.output),
                        }
                        for result in results
                    ],
                },
            ]
            response = step_tracker.run_once(
                f"{run_id}:model_call_after_tools",
                lambda: self._model_client.send(
                    messages=follow_up_messages, system=context.system, tools=tools
                ),
            )

        transcript_items.append(
            TranscriptItem(kind="message", payload={"role": "assistant", "text": response.text})
        )

        committed_state = self._session_store.commit(session_id, new_transcript_items=transcript_items)

        return RunResult(run_id=run_id, response=response, committed_state=committed_state)

    @staticmethod
    def _assistant_content_blocks(response: ModelResponse) -> list[dict[str, Any]]:
        """Reconstructed from ModelResponse's own fields, not response.raw —
        keeps the follow-up request buildable regardless of which model
        client produced the response."""
        blocks: list[dict[str, Any]] = []
        if response.text:
            blocks.append({"type": "text", "text": response.text})
        blocks.extend(
            {"type": "tool_use", "id": call["id"], "name": call["name"], "input": call["input"]}
            for call in response.tool_calls
        )
        return blocks
