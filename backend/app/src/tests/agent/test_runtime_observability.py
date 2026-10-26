import json
from typing import Any

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app.agent import runtime
from app.agent.model import ModelResponse
from app.agent.retriever import RetrievedPage
from app.agent.session import InMemorySessionRepository
from app.agent.tools import ToolDefinition, ToolRegistry


class _ModelClient:
    def __init__(self) -> None:
        self.responses = [
            ModelResponse(
                text="",
                tool_calls=[
                    {
                        "id": "call-1",
                        "name": "echo",
                        "input": {"message": "hello"},
                    }
                ],
                stops_reason="tool_use",
            ),
            ModelResponse(text="done", tool_calls=[], stops_reason="end_turn"),
        ]

    async def send(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        system_prompt: str | None = None,
    ) -> ModelResponse:
        del messages, tools, system_prompt
        return self.responses.pop(0)


class _Retriever:
    def select_with_metadata(self, query: str, limit: int) -> list[RetrievedPage]:
        del query, limit
        return [
            RetrievedPage(
                document_id="document-1",
                page_index=2,
                score=0.75,
                content=b"page-data",
            )
        ]


@pytest.mark.anyio
async def test_run_turn_records_runtime_spans_and_payloads(monkeypatch) -> None:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(runtime, "_TRACER", provider.get_tracer("test.runtime"))

    sessions = InMemorySessionRepository()
    session = sessions.create_session()
    tools = ToolRegistry()
    tools.register(
        ToolDefinition(
            name="echo",
            description="Return the message",
            input_schema={"type": "object"},
            handler=lambda arguments: arguments["message"],
        )
    )

    result = await runtime.run_turn(
        session_id=session.session_id,
        user_text="find the diagram",
        model_client=_ModelClient(),
        tool_registry=tools,
        session_repository=sessions,
        document_retriever=_Retriever(),
    )

    finished_spans = exporter.get_finished_spans()
    spans = {span.name: span for span in finished_spans}
    assert {
        "agent.runtime",
        "agent.session.load",
        "agent.retrieval",
        "agent.context.assemble",
        "agent.model.request",
        "agent.tool.execute",
        "agent.transcript.commit",
    }.issubset(spans)

    runtime_span = spans["agent.runtime"]
    assert runtime_span.attributes["session.id"] == session.session_id
    assert runtime_span.attributes["run.id"] == result.run_id
    assert all(
        span.context.trace_id == runtime_span.context.trace_id
        for span in finished_spans
    )
    model_spans = [
        span for span in finished_spans if span.name == "agent.model.request"
    ]
    assert len(model_spans) == 2
    assert [span.attributes["model.request_number"] for span in model_spans] == [1, 2]

    retrieval = json.loads(spans["agent.retrieval"].attributes["retrieval.pages"])
    assert retrieval == [
        {
            "document_id": "document-1",
            "page_index": 2,
            "score": 0.75,
            "content": {"encoding": "base64", "data": "cGFnZS1kYXRh"},
        }
    ]

    tool_span = spans["agent.tool.execute"]
    assert json.loads(tool_span.attributes["tool.input"]) == {"message": "hello"}
    assert json.loads(tool_span.attributes["tool.output"]) == "hello"
    context = json.loads(spans["agent.context.assemble"].attributes["context.messages"])
    image_block = context[0]["content"][1]
    assert image_block["data"] == {"encoding": "base64", "data": "cGFnZS1kYXRh"}

    transcript = sessions.get_state(session.session_id).transcript
    assert [item.run_id for item in transcript] == [result.run_id, result.run_id]

    provider.shutdown()
