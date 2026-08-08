# 0016 — Memory is written by the session's owner, not by the model, and is bounded

## Status

Accepted — 2026-08-08

## Context

Memory has been fully specified since [ADR 0004](0004-single-commit-path.md) gave
it its own write path and [ADR 0010](0010-bounded-context-window.md) decided how
it reaches the model. It is stored, persisted by the host, surfaced through the
system prompt, and covered by a conformance suite.

Nothing has ever written one.

`remember` and `forget` had no caller outside the tests, in this package or in
the application hosting it. So `state.memory` was empty on every real turn,
`assemble_context` took the `system is None` branch every time, and the renderer
had never executed in production. Memory was a complete pipeline with no
entrance — and, unlike `working_state`, one whose *read* side runs on every turn.
The documentation described a working feature throughout.

Two questions had to be answered together, because building the entrance without
the second is what makes the first dangerous.

**Who writes a memory?** The obvious answer is the model, via a `remember` tool.
It is how the feature is usually built, and it is what makes memory feel
autonomous.

**How much memory reaches the model?** `_format_memory` rendered every entry.
ADR 0010 bounds the message window and says nothing about memory, so memory was
the one channel into the context that nothing watched.

## Decision

**The session's owner writes memory; the model does not.** Memory is written
through the host's own surface by the authenticated owner of the session — in
this repository's host, `PUT`/`DELETE` on the session's memory. The model is
given no tool to write its own.

This is not only about approval being unbuilt. Memory feeds the system prompt on
every subsequent turn, so a model that can write memory can write its own future
instructions. One injected user message then becomes a persistent instruction
that survives every later turn in that session, and the injection outlives the
message that carried it. That makes `remember` one of the *higher*-risk tools to
expose, not the harmless one it looks like — it touches nothing outside our own
database, which is exactly why the risk is easy to miss.

The intuition runs the other way, so it is written down here: whoever next
reaches for "an easy first tool to give the model" should not reach for this one.

**Memory is bounded at assembly, most recent first**, default 20 to match the
message window. Bounded on the read side rather than at write, so the rule is
describable the same way the window is: "the twenty most recent memories" is
something a user can be told.

Selection sorts ascending and trims the front rather than sorting descending and
reversing. The two differ on ties, and entries written in one request do share a
timestamp.

Both bounds now treat 0 as 0. `history[-0:]` is the whole list, so asking for the
strictest possible bound previously returned everything — a bound that inverts at
its limit is worse than no bound, because the caller asked for the safe thing and
got the unsafe one.

## Consequences

The read path is live. `_format_memory` runs in production for the first time,
and the system prompt is no longer always absent.

Memory cannot be created by the conversation that motivates it. A user telling
the agent "always answer briefly" does not produce a memory; someone must write
one. That is a real loss of the feature's appeal, and the honest description of
what this buys is a *durable per-session preference store with an API*, not an
agent that learns.

Long-lived sessions silently lose their oldest memories, exactly as long
conversations silently lose their beginning. This is the consequence to dislike:
it is the same trade ADR 0010 accepted for messages, but a memory was kept
*deliberately*, where a message merely happened, so discarding one throws away
more intent. Twenty is a guess and will be wrong for someone.

Memory stays session-scoped. Starting a new session starts with none, so this is
not "the agent remembers me" — cross-session memory would re-key `remember` and
change `SessionRepository`, and that is a boundary change deserving its own
record rather than a column added quietly.

The model-facing tool is deferred, not rejected. When approval can pause and
resume a run, the decision above should be revisited *on its own merits* — the
security argument here is independent of the approval plumbing and does not
dissolve when the plumbing arrives.
