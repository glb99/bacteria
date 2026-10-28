"""
Fault tolerance test for the wrapped runtime.

Verifies that when a transient model failure occurs, the system recovers.
"""

import anyio

from app.agent.errors import ServingError
from app.agent.model import ModelResponse
from app.agent.retriever import RetrievedPage
from app.agent.runtime import run_turn_with_retry
from app.agent.session import InMemorySessionRepository
from app.agent.tools import ToolRegistry


class _FaultyModelClient:
    """Mock model client that fails once, then succeeds."""

    def __init__(self) -> None:
        self.attempt_count = 0

    async def send(
        self, messages: list[dict], tools=None, system_prompt=None
    ) -> ModelResponse:
        """Fail on first attempt, succeed on second."""
        self.attempt_count += 1

        if self.attempt_count == 1:
            raise ServingError("Transient error on first attempt")

        return ModelResponse(text="ok", tool_calls=[], stops_reason="end_turn")


class _PageRetriever:
    """Simple retriever that returns one page."""

    def select_with_metadata(self, query: str, limit: int) -> list[RetrievedPage]:
        return [
            RetrievedPage(
                document_id="doc", page_index=0, score=0.9, content=b"test-page"
            )
        ]


def test_runtime_recovers_from_transient_model_fault() -> None:
    """
    When the model call fails transiently, the wrapped runtime retries and succeeds.

    This test verifies the core fault tolerance feature: despite a transient failure,
    the system recovers automatically and completes the request.
    """
    # Setup: model that fails once, then succeeds
    model = _FaultyModelClient()
    sessions = InMemorySessionRepository()
    session = sessions.create_session()
    retriever = _PageRetriever()
    tool_registry = ToolRegistry()

    # Run: call run_turn_with_retry which should retry on ServingError
    result = anyio.run(
        lambda: run_turn_with_retry(
            session_id=session.session_id,
            user_text="test question",
            model_client=model,
            tool_registry=tool_registry,
            session_repository=sessions,
            document_retriever=retriever,
        )
    )

    # Assert: despite the fault, the request succeeded
    assert result.response.text == "ok"
    assert result.response.stops_reason == "end_turn"

    # Assert: the model was retried (called 2 times: failed once, succeeded on retry)
    assert model.attempt_count == 2, (
        f"Expected model to be called 2 times (failed once, retried), "
        f"but was called {model.attempt_count}. Retry mechanism may not be working."
    )
