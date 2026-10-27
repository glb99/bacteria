import base64
import json
import uuid
from dataclasses import dataclass
from typing import Any

from opentelemetry.trace import Span

from app.agent.context import assemble_context
from app.agent.model import ModelResponse, SendsToAgent
from app.agent.retriever import RetrievesDocumentPagesWithMetadata
from app.agent.session import SessionRepository, TranscriptItem
from app.agent.tools import ToolCall, ToolRegistry, ToolResult, execute_tool_call
from app.observability import get_tracer

MAX_TOOL_ROUNDS = 3

_TRACER = get_tracer(__name__)


@dataclass
class RunResult:
    run_id: str
    response: ModelResponse


def _assistant_content_blocks(response: ModelResponse) -> list[dict[str, Any]]:
    """Reconstruct the assistant turn from :class:`ModelResponse` fields.

    Built from the normalized fields rather than from ``response.raw``, so
    this works identically whichever provider produced the response —
    reading ``raw`` here would reintroduce exactly the provider coupling the
    protocol exists to remove.

    ``provider_data`` is forwarded verbatim and never inspected. The runtime
    does not know what is in it, does not need to, and must not drop it: for
    some providers it is a required continuation token, and losing it fails
    the follow-up call outright.
    """
    blocks: list[dict[str, Any]] = []
    if response.text:
        blocks.append({"type": "text", "text": response.text})
    blocks.extend(
        {
            "type": "tool_use",
            "id": call["id"],
            "name": call["name"],
            "input": call["input"],
            **(
                {"provider_data": call["provider_data"]}
                if "provider_data" in call
                else {}
            ),
        }
        for call in response.tool_calls
    )
    return blocks


def _trace_payload(value: Any) -> Any:
    if isinstance(value, bytes):
        return {
            "encoding": "base64",
            "data": base64.b64encode(value).decode("ascii"),
        }
    if isinstance(value, dict):
        return {str(key): _trace_payload(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_trace_payload(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _record_payload(span: Span, name: str, value: Any) -> None:
    span.set_attribute(name, json.dumps(
        _trace_payload(value), ensure_ascii=False))


def _follow_up_messages(
    messages: list[dict[str, Any]],
    response: ModelResponse,
    results: list[ToolResult],
) -> list[dict[str, Any]]:
    return [
        *messages,
        {"role": "assistant", "content": _assistant_content_blocks(response)},
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


async def _execute_tool_calls(
    tool_calls: list[ToolCall], tool_registry: ToolRegistry, tool_round: int
) -> list[ToolResult]:

    results: list[ToolResult] = []
    for call in tool_calls:
        with _TRACER.start_as_current_span("agent.tool.execute") as span:
            span.set_attribute("tool.name", call["name"])
            span.set_attribute("tool.call_id", call["id"])
            span.set_attribute("agent.tool_round", tool_round)
            _record_payload(span, "tool.input", call["input"])
            result = await execute_tool_call(call, tool_registry)
            _record_payload(span, "tool.output", str(result.output))
        results.append(result)
    return results


async def run_turn(
    session_id: str,
    user_text: str,
    model_client: SendsToAgent,
    tool_registry: ToolRegistry,
    session_repository: SessionRepository,
    document_retriever: RetrievesDocumentPagesWithMetadata,
    minimum_score: float | None = None,
) -> RunResult:

    run_id = str(uuid.uuid4())
    with _TRACER.start_as_current_span("agent.runtime") as runtime_span:
        runtime_span.set_attribute("session.id", session_id)
        runtime_span.set_attribute("run.id", run_id)

        with _TRACER.start_as_current_span("agent.session.load"):
            state = session_repository.get_state(session_id)

        with _TRACER.start_as_current_span("agent.retrieval") as retrieval_span:
            retrieval_span.set_attribute("retrieval.limit", 1)
            _record_payload(retrieval_span, "retrieval.query", user_text)
            retrieved_pages = document_retriever.select_with_metadata(
                query=user_text, limit=1
            )
            retrieval_span.set_attribute(
                "retrieval.page_count", len(retrieved_pages))
            _record_payload(
                retrieval_span,
                "retrieval.pages",
                [
                    {
                        "document_id": page.document_id,
                        "page_index": page.page_index,
                        "score": page.score,
                        "content": page.content,
                    }
                    for page in retrieved_pages
                ],
            )

        retrieved_documents = [
            page.content
            for page in retrieved_pages
            if minimum_score is None or page.score >= minimum_score
        ]
        with _TRACER.start_as_current_span("agent.context.assemble") as context_span:
            context = assemble_context(
                state=state,
                user_text=user_text,
                retrieved_documents=retrieved_documents,
            )
            context_span.set_attribute(
                "context.message_count", len(context.messages))
            _record_payload(context_span, "context.messages", context.messages)
            _record_payload(
                context_span, "context.system_prompt", context.system_prompt
            )

        tools = tool_registry.schemas_for_run() if tool_registry else None

        evidence = [
            TranscriptItem(
                kind="message",
                payload={"role": "user", "text": user_text},
                run_id=run_id,
            )
        ]

        def follow_up_messages(response: ModelResponse, results: list[ToolResult]):
            return _follow_up_messages(
                messages=context.messages, response=response, results=results
            )

        async def send_model_request(
            messages: list[dict[str, Any]], request_number: int
        ) -> ModelResponse:
            with _TRACER.start_as_current_span("agent.model.request") as span:
                span.set_attribute("model.request_number", request_number)
                span.set_attribute("model.tool_count", len(tools or []))
                _record_payload(span, "model.request.messages", messages)
                _record_payload(
                    span, "model.request.system_prompt", context.system_prompt
                )
                _record_payload(span, "model.request.tools", tools)
                response = await model_client.send(
                    messages=messages,
                    system_prompt=context.system_prompt,
                    tools=tools,
                )
                span.set_attribute(
                    "model.response.tool_call_count", len(response.tool_calls)
                )
                _record_payload(
                    span,
                    "model.response",
                    {
                        "text": response.text,
                        "tool_calls": response.tool_calls,
                        "stops_reason": response.stops_reason,
                    },
                )
                return response

        response = await send_model_request(context.messages, request_number=1)

        for tool_round in range(1, MAX_TOOL_ROUNDS + 1):
            if not response.tool_calls:
                break
            results = await _execute_tool_calls(
                tool_calls=response.tool_calls,
                tool_registry=tool_registry,
                tool_round=tool_round,
            )
            response = await send_model_request(
                follow_up_messages(response, results),
                request_number=tool_round + 1,
            )

        else:
            raise RuntimeError(f"tool loop exceeded {MAX_TOOL_ROUNDS} rounds")

        evidence.append(
            TranscriptItem(
                kind="message",
                payload={"role": "assistant", "text": response.text},
                run_id=run_id,
            )
        )

        with _TRACER.start_as_current_span("agent.transcript.commit") as span:
            span.set_attribute("transcript.item_count", len(evidence))
            _record_payload(
                span,
                "transcript.items",
                [
                    {
                        "kind": item.kind,
                        "payload": item.payload,
                        "run_id": item.run_id,
                    }
                    for item in evidence
                ],
            )
            for item in evidence:
                session_repository.commit(
                    session_id=session_id, new_transcript_item=item
                )

        return RunResult(run_id=run_id, response=response)
