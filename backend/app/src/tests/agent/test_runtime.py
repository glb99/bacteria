import anyio

from app.agent.model import ModelResponse
from app.agent.retriever import RetrievedPage
from app.agent.runtime import run_turn
from app.agent.session import InMemorySessionRepository
from app.agent.tools import ToolRegistry


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
