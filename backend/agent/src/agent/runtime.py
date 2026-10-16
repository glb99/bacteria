import uuid
from dataclasses import dataclass
from typing import Any

from agent.context import assemble_context
from agent.model import ModelResponse, SendsMessage
from agent.session import SessionRepository, TranscriptItem
from agent.tools import ToolRegistry, ToolResult, execute_tool_call

MAX_TOOL_ROUNDS = 3


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
    tool_calls: list[dict], tool_registry: ToolRegistry
) -> list[ToolResult]:

    results: list[ToolResult] = []
    for call in tool_calls:
        result = await execute_tool_call(call, tool_registry)
        results.append(result)
    return results


async def run_turn(
    session_id: str,
    user_text: str,
    model_client: SendsMessage,
    tool_registry: ToolRegistry,
    session_repository: SessionRepository,
) -> RunResult:

    run_id = str(uuid.uuid4())
    state = session_repository.get_state(session_id)
    context = assemble_context(state, user_text)
    tools = tool_registry.schemas_for_run() if tool_registry else None
    # tools_exposed = [schema["name"] for schema in tools or []]

    evidence = [
        TranscriptItem(kind="message", payload={"role": "user", "text": user_text})
    ]

    response = await model_client.send(
        messages=context.messages, system_prompt=context.system_prompt, tools=tools
    )

    for _ in range(MAX_TOOL_ROUNDS):
        if not response.tool_calls:
            break
        results = await _execute_tool_calls(
            tool_calls=response.tool_calls,
            tool_registry=tool_registry,
        )

        response = await model_client.send(
            messages=_follow_up_messages(
                messages=context.messages, response=response, results=results
            ),
            system_prompt=context.system_prompt,
            tools=tools,
        )

    else:
        raise RuntimeError(f"tool loop exceeded {MAX_TOOL_ROUNDS} rounds")

    evidence.append(
        TranscriptItem(
            kind="message", payload={"role": "assistant", "text": response.text}
        )
    )

    for item in evidence:
        session_repository.commit(session_id=session_id, new_transcript_item=item)

    return RunResult(run_id=run_id, response=response)
