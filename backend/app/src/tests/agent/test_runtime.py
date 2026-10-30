import anyio

from app.agent.errors import ServingError
from app.agent.model import ModelResponse
from app.agent.retriever import RetrievedPage
from app.agent.runtime import run_turn, run_turn_with_retry
from app.agent.session import InMemorySessionRepository
from app.agent.tools import ToolDefinition, ToolRegistry


class _PageRetriever:
    def __init__(self, page: RetrievedPage) -> None:
        self._page = page

    def select_with_metadata(self, query: str, limit: int) -> list[RetrievedPage]:
        return [self._page][:limit]


class _RecordingModel:
    def __init__(self) -> None:
        self.messages: list[dict] | None = None

    async def send(self, messages, tools=None, system_prompt=None) -> ModelResponse:
        self.messages = messages
        return ModelResponse(text="ok", tool_calls=[], stops_reason="end_turn")


class _ScriptedModelClient:
    """Returns the scripted responses in order, one per model request."""

    def __init__(self, responses: list[ModelResponse]) -> None:
        self._responses = iter(responses)

    async def send(self, messages, tools=None, system_prompt=None) -> ModelResponse:
        return next(self._responses)


class _ToolThenFaultModelClient:
    """Asks for the tool on every attempt until a tool result is in the conversation.

    The first follow-up call after a tool result fails transiently, once.
    """

    def __init__(self) -> None:
        self.faulted = False

    async def send(self, messages, tools=None, system_prompt=None) -> ModelResponse:
        has_tool_result = any(
            isinstance(message["content"], list)
            and any(block.get("type") == "tool_result" for block in message["content"])
            for message in messages
        )

        if not has_tool_result:
            return ModelResponse(
                text="",
                tool_calls=[{"id": "call-1", "name": "count", "input": {"text": "a"}}],
                stops_reason="tool_use",
            )
        if not self.faulted:
            self.faulted = True
            raise ServingError("Transient error after the tool ran")

        return ModelResponse(text="ok", tool_calls=[], stops_reason="end_turn")


class _FaultyModelClient:
    """Mock model client that fails once, then succeeds."""

    def __init__(self) -> None:
        self.attempt_count = 0

    async def send(self, messages, tools=None, system_prompt=None) -> ModelResponse:
        self.attempt_count += 1

        if self.attempt_count == 1:
            raise ServingError("Transient error on first attempt")

        return ModelResponse(text="ok", tool_calls=[], stops_reason="end_turn")


class _ToolThenTextModelClient:
    """Asks for the tool until a tool result is in the conversation, then answers."""

    async def send(self, messages, tools=None, system_prompt=None) -> ModelResponse:
        has_tool_result = any(
            isinstance(message["content"], list)
            and any(block.get("type") == "tool_result" for block in message["content"])
            for message in messages
        )

        if not has_tool_result:
            return ModelResponse(
                text="",
                tool_calls=[{"id": "call-1", "name": "count", "input": {"text": "a"}}],
                stops_reason="tool_use",
            )
        return ModelResponse(text="ok", tool_calls=[], stops_reason="end_turn")


class _CommitFailsOnceRepository(InMemorySessionRepository):
    """Fails the second transcript commit once, after the tool has run."""

    def __init__(self) -> None:
        super().__init__()
        self.commit_count = 0
        self.failed = False

    def commit(self, session_id: str, new_transcript_item) -> None:
        self.commit_count += 1
        if self.commit_count == 2 and not self.failed:
            self.failed = True
            raise ServingError("Transient error while committing the transcript")
        super().commit(session_id=session_id, new_transcript_item=new_transcript_item)


def _counting_tool(runs: list[str]) -> ToolDefinition:
    def handler(tool_input: dict) -> str:
        runs.append(tool_input["text"])
        return "ok"

    return ToolDefinition(
        name="count",
        description="Records one run.",
        input_schema={
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
        handler=handler,
    )


_PAGE = RetrievedPage(document_id="doc", page_index=0, score=0.9, content=b"test-page")


def test_run_turn_leaves_out_a_page_below_the_score_threshold() -> None:
    """A retrieved page below the caller's threshold is not sent to the model."""
    page = RetrievedPage(
        document_id="doc",
        page_index=3,
        score=0.2,
        content=b"page-png",
    )
    model = _RecordingModel()
    sessions = InMemorySessionRepository()
    session = sessions.create_session()

    anyio.run(
        lambda: run_turn(
            session_id=session.session_id,
            user_text="what is attention?",
            model_client=model,
            tool_registry=ToolRegistry(),
            session_repository=sessions,
            document_retriever=_PageRetriever(page),
            minimum_score=0.5,
        )
    )

    assert model.messages == [
        {"role": "user", "content": "what is attention?"},
    ]


def test_a_later_round_that_requests_the_tool_again_runs_it_again() -> None:
    """Guards the idempotency fix: a new request in round two is not a repeat.

    A fix that skips any tool name already run in this turn would break this.
    """
    runs: list[str] = []
    registry = ToolRegistry()
    registry.register(_counting_tool(runs))
    model = _ScriptedModelClient(
        [
            ModelResponse(
                text="",
                tool_calls=[{"id": "c1", "name": "count", "input": {"text": "a"}}],
                stops_reason="tool_use",
            ),
            ModelResponse(
                text="",
                tool_calls=[{"id": "c2", "name": "count", "input": {"text": "b"}}],
                stops_reason="tool_use",
            ),
            ModelResponse(text="done", tool_calls=[], stops_reason="end_turn"),
        ]
    )
    sessions = InMemorySessionRepository()
    session = sessions.create_session()

    anyio.run(
        lambda: run_turn(
            session_id=session.session_id,
            user_text="go",
            model_client=model,
            tool_registry=registry,
            session_repository=sessions,
            document_retriever=_PageRetriever(_PAGE),
        )
    )

    assert runs == ["a", "b"]


def test_retry_does_not_repeat_a_tool_that_already_ran() -> None:
    """
    The tool runs once, even though the run is retried after a fault.

    Today the retry starts the whole run again, so the tool runs a second time.
    """
    runs: list[str] = []
    registry = ToolRegistry()
    registry.register(_counting_tool(runs))
    model = _ToolThenFaultModelClient()
    sessions = InMemorySessionRepository()
    session = sessions.create_session()

    result = anyio.run(
        lambda: run_turn_with_retry(
            session_id=session.session_id,
            user_text="go",
            model_client=model,
            tool_registry=registry,
            session_repository=sessions,
            document_retriever=_PageRetriever(_PAGE),
        )
    )

    assert model.faulted, "the fault never fired, so no retry happened"
    assert result.response.text == "ok"
    assert runs == ["a"]


def test_runtime_recovers_from_transient_model_fault() -> None:
    """When the model call fails transiently, the wrapped runtime retries and succeeds."""
    model = _FaultyModelClient()
    sessions = InMemorySessionRepository()
    session = sessions.create_session()

    result = anyio.run(
        lambda: run_turn_with_retry(
            session_id=session.session_id,
            user_text="test question",
            model_client=model,
            tool_registry=ToolRegistry(),
            session_repository=sessions,
            document_retriever=_PageRetriever(_PAGE),
        )
    )

    assert result.response.text == "ok"
    assert result.response.stops_reason == "end_turn"
    assert model.attempt_count == 2, (
        f"Expected model to be called 2 times (failed once, retried), "
        f"but was called {model.attempt_count}. Retry mechanism may not be working."
    )


def test_retry_does_not_repeat_a_tool_when_the_transcript_commit_fails() -> None:
    """
    A commit that fails after the tool ran must not make the retry run the tool again.

    The tool result is committed as its own item before the failing commit,
    so the retry can reuse it.
    """
    runs: list[str] = []
    registry = ToolRegistry()
    registry.register(_counting_tool(runs))
    model = _ToolThenTextModelClient()
    sessions = _CommitFailsOnceRepository()
    session = sessions.create_session()

    result = anyio.run(
        lambda: run_turn_with_retry(
            session_id=session.session_id,
            user_text="go",
            model_client=model,
            tool_registry=registry,
            session_repository=sessions,
            document_retriever=_PageRetriever(_PAGE),
        )
    )

    assert sessions.failed, "the commit failure never fired, so no retry happened"
    assert result.response.text == "ok"
    assert runs == ["a"]
