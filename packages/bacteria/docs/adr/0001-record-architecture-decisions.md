# 0001 — Record architecture decisions in this repository

## Status

Accepted — 2026-08-06

## Context

This system is small, and almost every part of it is smaller than it could be:
no persistence, one round of tool calls, a blunt context window, approval
without authorization. Read cold, those look like an unfinished project.

Most of them are not. They are decisions, each with a reason, and the reasons
are the actual value of the codebase — the code implementing a recent-message
window is fifteen lines, while the argument for preferring it to summarization
is the part that transfers to the next system.

That reasoning has nowhere durable to live. Commit messages are ordered by
accident of when something was touched. Code comments explain a line, not a
direction. A single design document accumulates until nobody reads it and
nothing in it can be superseded without editing history.

## Decision

Record each significant architecture decision as a numbered file in `docs/adr/`,
in Nygard format: Status, Context, Decision, Consequences.

Records are immutable. A decision that stops being true is superseded by a new
record rather than edited, so the reversal keeps its own reasoning.

Records 0002–0013 were written in one pass, retroactively, from an existing
design document. Their Context sections describe the situation at the time each
decision was made, not the situation when they were transcribed.

A decision qualifies when it constrains future work, when a reasonable engineer
would choose differently, or when it is a deliberate omission that will look
like a bug. Library choices and formatting conventions do not qualify.

## Consequences

The rationale survives being separated from the conversation that produced it —
which is the actual test, since anyone arriving later has only the repository.

Decisions become individually reversible. Superseding one is a new file, not
surgery on a document holding twelve unrelated things.

The index in `README.md` is maintained by hand and will drift if a record is
added without updating it.

There is a standing temptation to write a record for every choice. Resisting it
matters: thirty records nobody reads is the same failure as the design document
this replaces, arrived at by a different route.
