"""Runtime — Part 4 (Runtimes, Workflows, and Durable Execution).

Owns turn-level sequencing: generates a lightweight run identity, orchestrates
calls into the model client and session store, and enforces step-boundary
discipline around side effects so a step is never blindly re-executed.

In-memory only — no persistence, no replay/resume-after-crash. That's a
deliberate scope decision (see docs/SYSTEM_DESIGN.md, Part 4), not an
oversight: a run's identity and step history live only for the duration of
one turn and are discarded afterward.

Context assembly (what messages actually get sent to the model) is a minimal
stub here — real design belongs to Part 5 (Context, Retrieval, and Memory).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

from bacteria.model.client import ModelResponse
from bacteria.session.store import SessionState, SessionStore, TranscriptItem


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

    def run_turn(self, session_id: str, user_text: str) -> RunResult:
        run_id = str(uuid.uuid4())
        step_tracker = StepTracker()

        state = self._session_store.get_state(session_id)
        messages = self._transcript_to_messages(state.transcript) + [
            {"role": "user", "content": user_text}
        ]

        response: ModelResponse = step_tracker.run_once(
            f"{run_id}:model_call",
            lambda: self._model_client.send(messages=messages),
        )

        committed_state = self._session_store.commit(
            session_id,
            new_transcript_items=[
                TranscriptItem(kind="message", payload={"role": "user", "text": user_text}),
                TranscriptItem(kind="message", payload={"role": "assistant", "text": response.text}),
            ],
        )

        return RunResult(run_id=run_id, response=response, committed_state=committed_state)

    @staticmethod
    def _transcript_to_messages(transcript: list[TranscriptItem]) -> list[dict[str, Any]]:
        """Minimal stub — revisit in Part 5 (context assembly)."""
        return [
            {"role": item.payload["role"], "content": item.payload["text"]}
            for item in transcript
            if item.kind == "message"
        ]
