---
date: 2026-10-29
status: exploring
question: "What is _call_either for?"
adr: ""
---

# What is `_call_either` for?

## Why this session

The person asked what `_call_either` is for. Which decision that answer would change is still open.

## Starting model

| Prompt | Answer |
| --- | --- |
| What do you currently believe? | It lets the agent execute tool calls whether the tool is defined as sync or async. Revised: "that it is not the function for" (the person's correction, not yet explained). |
| Which decision does this understanding change? | Not answered yet. |

## Evidence

- `backend/app/src/app/agent/tools.py:144-149`: `_call_either` checks `inspect.iscoroutinefunction(fn)`. Async handlers are awaited directly. Sync handlers run through `anyio.to_thread.run_sync`, so they do not block the event loop.
- `backend/app/src/app/agent/tools.py:164`: `execute_tool_call` is its only call site. It passes `tool.handler` and the tool input.
- `build_add_note_tool` (line 172) defines a sync handler, so it takes the thread path.

## Inferences

-

## Shared model

## Gaps

- The person says `_call_either` is not the function for running sync or async tool calls. Their later reading is that it avoids a slow tool blocking the loop. Not yet confirmed by the person.
- Source of the stated purpose: `C:\Users\guill\Documents\Projects\bacteria-core\backend\agent\src\bacteria\agent\tools\execution.py:16-24` (invariant: a sync handler never runs on the event loop thread) and `:69-83`. The same helper also runs the approval gate (`:171`), which this repo's copy does not have.
- The stale path in `tools.py:17` points to `bacteria-core`'s `execution.py`, not to a file in this repo.

## Alignment check

| Question | Answer that matches the shared model | Person's answer | Match |
| --- | --- | --- | --- |
| | | | |

## Handoff for a human ADR

No ADR is indicated yet. The decision this understanding would change is still open.
