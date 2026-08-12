# 0007 — Treat tool calls as proposals and isolate execution in one module

## Status

Accepted — 2026-08-06

## Context

A model that requests a tool has done exactly one thing: produced text naming a
function and some arguments. Nothing has happened yet. The gap between that and
the function running is where every meaningful control lives — does the tool
exist, is this permitted, did anyone agree, what is the blast radius.

The convenient implementation closes that gap invisibly. Most quickstarts read
`for call in response.tool_calls: handlers[call.name](call.input)`, inside
whatever loop already had the response to hand. There is no seam left to put a
check in, and no single place to look when asking what in the system can cause
a side effect.

There is a second, quieter version of the same problem: a model client that
executes what it reports. Then retrying a failed request re-runs a side effect,
and the retry logic has no way to know.

## Decision

`execute_tool_call()` in `tools/execution.py` is the only place a handler is
called. Nothing else invokes one.

Model clients report proposals and cannot do otherwise: `model/` imports no tool
module, no filesystem, no subprocess. That is what makes retries provably
side-effect free — there is nothing there to repeat.

The runtime decides *when* execution happens; it does not decide *how* a call is
authorized or run, and it does not call handlers itself.

Order inside `execute_tool_call` is part of the contract: resolve, then approve,
then run. Approval comes after resolution so the prompt can describe a real
tool, and before the handler so a rejection means nothing happened.

## Consequences

"What can cause a side effect in this system?" has a one-file answer, and every
guard that should apply to a side effect has one obvious place to live.

Retry safety in the model client is structural rather than argued.

Every proposal costs a registry lookup and an approval call. Irrelevant here,
and worth naming as the price of the indirection.

The taxonomy is coarse: unknown tool, rejected, and handler-raised all surface
as `ToolExecutionError`. Callers treat them identically — the run stops and the
attempt is recorded — so one type is enough until something needs to branch.

Isolation is *not* covered by this decision and is frequently assumed to be.
Concentrating execution makes a sandbox easy to add later; it adds none. A
handler still runs in-process with full privileges. See `tools/execution.py`.
