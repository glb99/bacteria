import time

import anyio

from app.agent.tools import ToolDefinition, ToolRegistry, execute_tool_call


def _slow_sync_handler(tool_input: dict) -> str:
    time.sleep(0.3)
    return "done"


async def _ticks_during_slow_tool() -> int:
    ticks: list[None] = []

    async def ticker() -> None:
        while True:
            ticks.append(None)
            await anyio.sleep(0.01)

    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="slow",
            description="blocks for a while",
            input_schema={"type": "object"},
            handler=_slow_sync_handler,
        )
    )

    async with anyio.create_task_group() as tg:
        tg.start_soon(ticker)
        await anyio.sleep(0.05)
        before = len(ticks)
        await execute_tool_call({"id": "1", "name": "slow", "input": {}}, registry)
        during = len(ticks) - before
        tg.cancel_scope.cancel()

    return during


def test_event_loop_keeps_running_while_a_sync_tool_runs() -> None:
    """A slow sync tool runs off the loop thread, so other tasks keep ticking."""
    assert anyio.run(_ticks_during_slow_tool) > 0
