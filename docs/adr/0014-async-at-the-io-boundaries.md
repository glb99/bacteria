# 0014 — Make the I/O boundaries async; keep the pure layers synchronous

## Status

Accepted — 2026-08-06

## Context

Every layer here is synchronous. That was free while the only entry point was a
CLI serving one user, one turn at a time.

The system is now being wrapped in a service that will host it: an HTTP API, a
queue worker, and — the case that forces the question — real-time audio
streaming. Those are async top to bottom.

The blocking surface is small and sits entirely at layer edges: the two model
clients' provider calls, the `time.sleep` in the model client's retry loop, the
tool handler invocation, and the interactive approval prompt. Everything
else — context assembly, registry lookup, failure classification, output
validation, the in-memory store — is computation with no I/O in it.

The obvious cheap option is to leave all of it synchronous and have the service
call `run_turn` in a worker thread. It requires no change here at all.

It fails on a specific number. A turn is dominated by model latency — seconds,
doubled when a tool round follows — and under a threadpool each concurrent turn
holds an OS thread for that entire wait. anyio's default limiter is 40 threads,
so concurrency caps in the low tens, reached at a few dozen users. Streaming
makes it worse: yielding tokens out of a worker thread means bridging through a
queue, which is a hand-built event loop with fewer guarantees than the one
already running.

A threadpool is still the right tool somewhere: tool handlers are arbitrary
code, most of it synchronous, and rewriting every tool as a coroutine would be a
tax paid by tool authors for no gain.

There is a second question underneath. `SessionStore` performs no I/O today —
it is a dict — but `session/store.py` documents persistence as "a second
implementation of this class, not a change to any caller." A synchronous
interface makes that promise false the moment the backing store is Postgres.

## Decision

Async at the boundaries that touch I/O; synchronous everywhere else.

Async: `SendsMessages.send`, `Runtime.run_turn`, `execute_tool_call`, the
approval gate, and the `SessionStore` interface.

Synchronous: `context/`, `tools/registry`, `model/errors`, `model/output` — pure
functions, where a coroutine buys nothing and costs a keyword at every call
site.

`execute_tool_call` awaits a coroutine handler and runs a synchronous one in a
worker thread. Both kinds of tool stay first-class.

The retry loop stays as it is, hand-written in each client, with `time.sleep`
becoming `await anyio.sleep`. Replacing it with a retry library was considered
and rejected — see Consequences.

`SessionStore` goes async now, ahead of any persistent implementation, so that
adding one remains what the module says it is.

Streaming is explicitly **not** part of this. It is a second protocol method
(`send_stream`) and a separate record, not a widening of `send`.

## Consequences

Concurrency stops being bounded by thread count. Turns waiting on a provider
cost a coroutine each instead of a thread each.

The in-memory `SessionStore` grows `async def` methods wrapping dictionary
operations, which look absurd in isolation. That is the price of the seam
staying honest, and it is paid once.

Every caller of `run_turn` becomes async, including the CLI, which now needs an
`asyncio.run` at its edge. The test suite moves to `anyio`/`pytest-asyncio`;
roughly ten files are affected.

Two model clients must be rewritten against their SDKs' async variants. The
translation logic in `gemini_client` is untouched — only the call and the
`await` around it change.

The retry loop keeps a property it should not keep for long: linear backoff with
no jitter. That was justified at one concurrent caller and stops being justified
the moment this runs behind a service, where everything that failed together
retries together. `stamina` was adopted for exactly this and then backed out —
it was the right library and the wrong time, bundling a library choice into a
boundary decision where it could not be reversed independently, for jitter no
current caller needs. When a second concurrent caller exists, revisit it; the
change is confined to two `send` methods and the tests assert call counts rather
than mechanism, so either version satisfies them.

A synchronous consumer of this package no longer exists. Anyone embedding the
agent must bring an event loop. Given the intended host is a service, that is
not a real cost today, but it is a door closing.

The pure layers staying synchronous means the async boundary is visible in the
type signature of every function that crosses it. That is intentional — a
coroutine in this codebase now means "this touches the outside world."
