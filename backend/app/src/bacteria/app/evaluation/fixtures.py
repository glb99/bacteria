"""Runs to judge, produced on purpose.

The honest limitation, stated where it cannot be missed: these are runs this
project built to exercise its own checks, not runs anyone had. Judging them
tells you the system still behaves the way it was designed to — real regression
value — and tells you nothing about how it behaves in front of people. Part 8's
feedback loop starts from *production* failures, and this is not that.

Fixtures rather than captured traffic because captured traffic is a decision
nobody has made yet. Real transcripts hold user text verbatim, there is no
retention rule and no way to delete one, and building a gate that depends on
keeping them would settle that question by accident, in the direction of
keeping everything.

Every scenario drives the real :class:`~bacteria.agent.runtime.runtime.Runtime`
against the real repository. Only the model is faked. A fixture that inserted
transcript rows directly would be writing the answer the checks then read back,
and would keep passing after the runtime stopped producing that shape at all.
"""

import contextlib
from typing import Any

from bacteria.agent.model.protocol import ModelResponse
from bacteria.agent.runtime.runtime import Runtime
from bacteria.agent.session.protocol import SessionRepository
from bacteria.agent.tools.execution import ToolExecutionError
from bacteria.agent.tools.registry import ToolDefinition, ToolRegistry

FIXTURE_MODEL = "fixture-model-1"
"""The model every seeded run reports.

Fixed so a policy can assert on it. It is deliberately not a real model name —
a fixture claiming to be `claude-sonnet-4-5` invites someone to read a report
over seeded data as though it described production.
"""

FIXTURE_TOOL = "get_time"


class _ScriptedClient:
    """Replies with whatever the scenario asked for, in order.

    Not a mock library: the scenarios need a client that proposes a tool call on
    one turn and answers plainly on the next, and expressing that as a list of
    prepared replies is shorter than configuring it.
    """

    def __init__(self, replies: list[ModelResponse]) -> None:
        self._replies = list(replies)

    async def send(self, messages: list[dict[str, Any]], **kwargs: Any) -> ModelResponse:
        if not self._replies:
            raise AssertionError("scripted client ran out of replies")
        reply = self._replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


class _FailingClient:
    async def send(self, messages: list[dict[str, Any]], **kwargs: Any) -> ModelResponse:
        raise RuntimeError("model backend unavailable")


def _text(text: str) -> ModelResponse:
    return ModelResponse(
        text=text, tool_calls=[], stop_reason="end_turn", raw=None, model=FIXTURE_MODEL
    )


def _tool_request() -> ModelResponse:
    return ModelResponse(
        text=None,
        tool_calls=[{"id": "t1", "name": FIXTURE_TOOL, "input": {}}],
        stop_reason="tool_use",
        raw=None,
        model=FIXTURE_MODEL,
    )


def _registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name=FIXTURE_TOOL,
            description="returns the current time",
            input_schema={"type": "object"},
            handler=lambda tool_input: "10:00",
        )
    )
    return registry


async def seed(repository: SessionRepository, user_id: str = "evaluation-fixtures") -> str:
    """Produce one session containing every shape the checks distinguish.

    Four runs, chosen so that each check has both something to pass and — in the
    tests that mutate this — something to catch:

    1. a plain turn,
    2. a turn that proposes and executes a tool,
    3. a turn whose tool call is refused, which must leave a `rejected` record
       carrying no output,
    4. a turn whose model call fails, which must still describe itself.

    Runs 3 and 4 raise by design; the exceptions are caught here because the
    evidence they leave behind is the reason they are in the fixture at all.

    Returns:
        The session id, so a caller can scope a report to exactly these runs
        rather than to whatever else the database holds.
    """
    session = await repository.create_session(user_id=user_id)
    session_id = session.session_id

    plain = Runtime(model_client=_ScriptedClient([_text("hello")]), session_store=repository)
    await plain.run_turn(session_id, "hello there")

    with_tool = Runtime(
        model_client=_ScriptedClient([_tool_request(), _text("It's 10:00")]),
        session_store=repository,
    )
    await with_tool.run_turn(session_id, "what time is it?", tool_registry=_registry())

    refused = Runtime(model_client=_ScriptedClient([_tool_request()]), session_store=repository)
    with contextlib.suppress(ToolExecutionError):
        await refused.run_turn(
            session_id,
            "what time is it?",
            tool_registry=_registry(),
            approve=lambda _tool_call: False,
        )

    broken = Runtime(model_client=_FailingClient(), session_store=repository)
    with contextlib.suppress(RuntimeError):
        await broken.run_turn(session_id, "this one cannot work")

    return session_id
