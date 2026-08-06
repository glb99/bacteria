# 0008 — Ask for approval at the side effect, and default to denied

## Status

Accepted — 2026-08-06

## Context

Three controls get collapsed into each other constantly, and they are not the
same thing:

- **authorization** — is this principal permitted this capability at all?
- **approval** — should this particular call, with these arguments, run now?
- **isolation** — if it runs and goes wrong, how far does the damage reach?

Only one of them means anything at this scale. Authorization needs principals to
distinguish and a policy to evaluate; there is one local user. Isolation needs
containment infrastructure. Approval, by contrast, is answerable the moment any
tool has a real side effect, even with a single user.

Two ways to build approval such that it looks present and does nothing. Ask too
early — "may I help with your files?" at the start of a task — and by the time a
deletion happens ten steps later, the user has agreed to something they could
not have seen. Or accept ambiguous input as consent, so a stray newline, a
hedged "sure", or a piped EOF authorizes an action.

## Decision

Build approval. Defer authorization and isolation entirely, with no stubs or
placeholders, and name all three in `tools/approval.py` so the missing two stay
visible rather than being assumed covered by the one that exists.

Prompt at the side effect, inside `execute_tool_call`, immediately before the
handler runs — not at task start and not at turn start.

Show the arguments, not just the tool name. "Approve `send_email`?" and "approve
`send_email` to this address?" are different questions and only the second can
be answered correctly.

Default to denied. Only an explicit `y` or `yes` approves; everything else
rejects.

A rejection fails the turn loudly. It is not caught and reported back to the
model as a soft failure — a model told "that was refused" tends to try a
variation, which is the opposite of what a refusal meant.

## Consequences

The gate is real, and it gates something real: `add_note` exists partly so that
approval is tested against an actual side effect rather than a no-op.

Denial is the safe failure. A wrongly refused call is recovered by asking again;
a wrongly approved one has already happened.

`cli_approve` blocks on stdin, so no non-interactive surface can use it — no
server, no scheduled run. Those need a different implementation of the same
`(ToolCall) -> bool` shape, which needs durable run state ([ADR
0003](0003-in-memory-state.md)) to pause and resume around a human.

Every call is asked about individually; there is no "always allow this tool".
Mildly tedious, and deliberate — a remembered grant scoped too broadly is the
failure mode approval exists to prevent.

Failing the turn on rejection is blunt. A graceful "the user declined" round trip
would be friendlier and is not built, because the simple behavior is correct and
the friendly one requires deciding what the model should be told.
