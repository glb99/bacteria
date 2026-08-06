# 0011 — Run one round of tool execution per turn

## Status

Accepted — 2026-08-06

## Context

Once tool execution works, the obvious next step is to loop: keep calling the
model until it stops asking for tools. That is what makes an agent capable of
multi-step work — read a file, decide, write another — instead of one lookup
followed by an answer.

It is also where an agent starts being able to spend unbounded money and time on
its own. A loop needs a round cap, and a cost budget, and a policy for what
happens when round four fails after rounds one through three already had side
effects. That last one is genuinely hard: the run is now partially applied, and
neither continuing nor stopping is obviously right.

None of that machinery is useful without a tool set that rewards multi-step
reasoning. There is currently one tool, which appends a line to a file.

## Decision

Exactly one round per turn: call the model, execute any tools it proposed, call
the model once more with the results, return.

A model that wants a second round after seeing results does not get one — its
follow-up response is the final answer for that turn.

Record what lifting this would require, in `runtime/runtime.py`, so the
constraint is visibly a decision rather than an unfinished loop.

## Consequences

A turn's cost is bounded and knowable in advance: at most two model calls and
one batch of tool executions. Nothing can spend without limit.

The runtime stays short enough to read in one pass, which is most of what makes
its ownership boundaries checkable.

Genuinely multi-step tasks are out of reach. This is the ceiling on what the
agent can do, and it is the decision that most directly limits capability rather
than robustness.

Because the second model call is final, a model that uses its tool result to
decide it needs a different tool has no way to say so — it answers with what it
has. Whether that produces a wrong answer or an honest "I could not determine
this" is entirely up to the model, which is unsatisfying and is the clearest
argument for revisiting this.

Lifting it later is confined to `run_turn`, but is not merely a `while` loop: the
round cap, the budget, and the partial-failure policy all have to be decided at
the same time.
