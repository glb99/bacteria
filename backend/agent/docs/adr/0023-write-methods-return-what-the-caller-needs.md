# 0023 — Write methods return what the caller needs, not the whole session

## Status

Accepted — 2026-08-11

## Context

Every write method on `SessionRepository` ended with `return await self.get_state(session_id)`.
That is a full re-read: the entire transcript, all session memory, all
proposals, and — since [ADR 0021](0021-memory-is-scoped-to-a-session-or-a-user.md)
— all user memory. Four queries, one of them unbounded.

So a turn read the whole conversation twice. Once at the start, deliberately, to
assemble context. Once at the end, incidentally, to build a `SessionState` that
nothing reads.

Nothing is the literal count. Grepping every call site in both packages:

- `commit`, `propose`, `forget`, `reject` — return value discarded at every
  production call site.
- `remember`, `activate` — return value used, and used to pull out exactly one
  `MemoryEntry`. The route wanted one row and was handed the conversation.

`RunResult.committed_state` carried the same waste outward, and its own docstring
already told callers not to trust it: *"A snapshot, not a live view; re-read from
the store for anything current."* A field that documents its own uselessness and
has no reader is the pattern this project deletes wherever it finds it — the same
argument that kept `score` off `Selection` two ADRs ago.

The cost grows. The transcript read is O(conversation length), so the waste is
not a constant overhead but a slope, and it lands on the hot path.

## Decision

A write method returns what its callers actually use.

`commit`, `propose`, `forget` and `reject` return `None`. `remember` and
`activate` return the `MemoryEntry` they just wrote.

`RunResult.committed_state` is removed.

**Returning the entry costs nothing.** Both implementations already hold the
object they just constructed, so `remember` and `activate` do no read at all
where they previously did four.

**`None` rather than a cheaper snapshot.** A store that returned, say, just the
`Session` would still be answering a question nobody asked. The honest signature
for an operation whose result is "it is written" is one that returns nothing, and
callers wanting current state call `get_state`, which is what the field they were
using already advised.

**The protocol shrinks in surface without shrinking in guarantees.** ADR 0015
was protecting the number of *write paths*, not the richness of return types;
`commit` remains the single path for turn state.

## Consequences

Measured against Postgres, on a five-turn conversation:

| Operation | SELECTs before | after |
|---|---|---|
| One turn | 12 | 7 |
| One `remember` | 7 | 2 |

The five removed from each are one `get_state`: the session row, the whole
transcript, session memory, proposals, and user memory. The transcript one grows
with the conversation, so the saving is a slope rather than a constant.

The routes get simpler rather than more complex. `write_memory` and
`activate_proposal` were reaching into `state.user_memory if scope == USER_SCOPE
else state.memory` to find the entry they had just written; they now receive it.
That conditional existed only because the return type was too big.

`test_commit_is_the_only_way_state_actually_changes` asserted on `commit`'s
return value and now asserts through `get_state`. It reads better for it: the
claim is that state changed *in the store*, and reading the store is a more
direct way to check that than trusting what the writer said about itself.

The affordance genuinely lost: a caller can no longer get post-write state in one
round trip, and one that wants it now makes a second call. That is a real
regression for anything needing read-after-write atomicity — and nothing here
needs it, because `commit` is already the only writer of turn state and the SQL
implementation holds a row lock for the duration.

Reintroducing a return value later is additive and cheap. Removing one is not,
which is why this is worth doing while the only reader is a test.
