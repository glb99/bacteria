# 0003 — Keep all state in memory; defer persistence and durable execution

## Status

Accepted — 2026-08-06

## Context

Two related capabilities are conventionally expected of an agent framework:
session state that outlives the process, and runs that can be resumed after a
crash. Neither exists here.

The pull toward building them early is strong, because both are structural — the
usual claim is that retrofitting persistence is expensive and it is cheaper to
have it from the start.

Against that: the deployment is a single local user running an interactive CLI.
There is no crash-mid-long-workflow scenario, because a turn lasts seconds and
the user is watching it. And durability done approximately is worse than
durability absent. Retry, replay, resume, and idempotency are four different
properties that are routinely conflated; a system that persists a checkpoint but
gets step boundaries wrong resumes into a state where a side effect runs twice.
That failure is silent, and it inspires confidence it has not earned.

## Decision

No persistence. Sessions live in a process-local dict and are lost on exit. No
run store, no checkpointing, no replay, no resume.

Build the parts of durable execution that do not require a backing store, since
they are load-bearing on their own: explicit run identity, and `StepTracker`,
which refuses to run a step id twice within a run.

State the weakness precisely rather than letting the presence of `StepTracker`
imply more than it delivers. It provides idempotency *within* a run. Idempotency
across restarts is a different property and is not provided.

Keep the seam correct so this stays additive. `SessionStore`'s four public
methods are the complete operation set a backing store would implement, so
persistence is a second implementation plus a way to select one — not a change
to any caller.

## Consequences

Nothing is remembered between invocations. Memory works within a session and
cannot survive one, which is the most user-visible limitation in the system.

A process that dies mid-turn loses the turn entirely.

The absence is honest and located: the gap is documented in `session/store.py`
and `runtime/runtime.py`, at the exact points it would be filled.

Adding persistence later drags in two things beyond a storage backend:
serialization for `TranscriptItem` and `MemoryEntry`, and concurrency control,
because a shared store means `commit` stops being the only writer and needs a
staleness check. [ADR 0004](0004-single-commit-path.md) keeps a single place for
that check to go.

If this system ever grows long-running or multi-step autonomous work, this
decision is the first one to revisit, and it blocks several others.
