# 0004 — Route every state change through a single commit path

## Status

Accepted — 2026-08-06

## Context

Model output is a suggestion. So is anything the runtime derives from it. The
model cannot see concurrency, ordering, or what the record looks like right now,
so it cannot be trusted to decide what becomes canonical — and neither can code
holding a stale copy of state.

The first implementation made this a two-step API: `propose()` produced a
proposal object, `commit()` applied it. It read well and mirrored the concept
directly.

In practice `propose()` validated the session id and constructed a dataclass.
Neither is the guarantee that matters. The guarantee is that exactly one
deterministic, non-model code path writes — and a second method placed before it
does not strengthen that at all.

A separate concern with the same root: if `get_state` returned a live reference,
any caller could mutate authoritative state from outside the module that owns
it. The invariant would then hold only for as long as every caller behaved, and
the resulting bug — the record changing with no record of who changed it — is
close to untraceable.

## Decision

One write path per kind of state. `commit()` for transcript and working state;
`remember()` and `forget()` for memory ([ADR
0010](0010-bounded-context-window.md) covers why memory is separate).

`commit()` takes the change as plain arguments. The removed `propose()` step is
not reinstated; a future staleness or conflict check belongs *inside* `commit()`,
which is precisely why it stays the single write path while it is still thin.

`get_state()` returns a deep copy. This is the enforcement mechanism, not a
defensive nicety — it is what makes the invariant a property of the code rather
than a rule people follow.

## Consequences

The invariant is structural and directly testable: mutate what `get_state`
returns, read again, observe nothing changed.

Adding concurrency control later has exactly one place to go.

Deep-copying on every read costs time and memory proportional to transcript
size. At one user and a bounded conversation this is irrelevant; at scale it
would need revisiting, most likely via immutable structures rather than by
weakening the guarantee.

The API is less self-describing than `propose`/`commit` was. The proposal
concept now lives in documentation rather than in a method name — accepted,
because the alternative was a method that existed to describe an idea rather
than to enforce it.
