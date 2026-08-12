# 0019 — A run records how it was configured

## Status

Accepted — 2026-08-11

## Context

[ADR 0018](0018-transcript-items-carry-their-run-id.md) made a run
*identifiable*: every item it commits carries its `run_id`, so the evidence a
turn produced can be selected. It did not make a run *explicable*. The
transcript says what was said and which tools ran, and nothing about the
conditions the run happened under.

So two runs that produced the same words are indistinguishable in the record,
even when they were entirely different events. One may have been answered by
Claude and the other by Gemini — `model_provider` is a deployment setting read
per request, and no turn writes down which way it was set. One may have been
shown twenty memories and the other none. One may have been offered a tool the
other never saw.

The same gap makes evaluation impossible rather than merely absent. The article
this design follows separates deterministic checks — did the run call the right
tool, use the right model, get approval before the side effect — from rubric
judgment of the final answer, and insists the deterministic ones be assertions
rather than a model's opinion. Every one of those assertions reads a property of
the run. None of them can be written against a record that holds only prose.

There is a narrower version of the same problem inside tool failures. Unknown
tool, refused by approval, and handler raised are all `ToolExecutionError` with
`status: "failed"`, distinguished only by the wording of a message. "The model
asked to do something and a boundary stopped it" and "the model asked to do
something and it crashed" are opposite facts about the system — the first says a
control worked — and recovering that difference by string-matching an error
makes the meaning of stored evidence depend on how an exception was phrased.

## Decision

Every run appends exactly one `run_meta` transcript item, on both exit paths,
recording: the model that answered, the tools exposed, how many messages and
memories were in context, how many tool calls were proposed, how many were
dropped, and the outcome.

Failed `tool_call` records gain a structural `reason` — `unknown_tool`,
`rejected`, or `handler_error` — carried on the exception as a value.

**In the transcript, not a `runs` table.** A table is the better long-term home
and is what durable, resumable runs will eventually need. It is wrong now
because it costs a second write. [ADR 0004](0004-single-commit-path.md) has one
commit path and [ADR 0012](0012-commit-evidence-on-failure.md) depends on that
single write surviving a failure; a separate runs table would either need its
own write, which can fail independently and is exactly the write most likely to
be skipped on the failure path, or need `commit` to accept run metadata — which
is this decision with extra machinery. Run metadata is evidence, and evidence
already has a home.

The transcript is an event log rather than a script, so this fits what it
already holds. Assembly selects `kind == "message"`, so `run_meta` cannot reach
a model.

**`model` on `ModelResponse`, not on `SendsMessages`.** Asking a client which
model it holds would widen the protocol [ADR 0005](0005-narrow-model-protocol.md)
deliberately keeps to one method. It would also answer a different question:
configuration is an intention, and a client that fell back or routed elsewhere
would still report the intention. Both SDKs report what actually served the
request — Anthropic as `model`, Gemini as `model_version`, which resolves a
pinned alias to a specific build — so the honest source is the response.

**Counts, not copies.** Recording the assembled messages verbatim would
duplicate the transcript into itself and grow quadratically, and would put the
system prompt's contents somewhere with its own retention question. What a
reader needs is how much the model was shown.

**`tool_calls_dropped` is recorded** even though nothing acts on it. [ADR
0011](0011-single-round-tool-loop.md) allows one round per turn, so a second
response asking for more tools is silently discarded. Until now, a model that
wanted to continue and a model that was finished produced identical evidence.
That is a cost of 0011 that should be visible where 0011's effects are.

## Consequences

A deterministic eval becomes writable. "Every run in this session used the
pinned model", "no run was offered a tool outside this set", "a refusal was
recorded before any side effect" are now queries over stored evidence rather
than properties nobody kept.

A failed run explains itself as fully as a successful one, including the case
where it failed before anything answered — `model` is then `null`, and that null
is the finding rather than a gap.

Every turn writes one more row. At one item per run this is small next to the
messages a turn already writes, and it is the cost of a transcript being
reconstructable rather than only readable.

`run_meta` is a fourth `TranscriptItemKind`, so every exhaustive reader of that
`Literal` must handle it — which is what the closed type is for. Two runtime
tests counted raw transcript length and now count by kind; that they broke is
the type working, but any external consumer counting rows will break the same
way without the same warning.

The evidence now names the model and the tools a deployment has. That is a small
increase in how sensitive a transcript is, arriving on top of the unsolved
retention question ADR 0012 already flagged.

Still unrecorded: latency and token cost, the prompt or tool-schema version, the
approval decision on calls that *succeeded* (a refusal is now visible; a grant
still looks the same as never having asked), and the identity the run acted
under. The last belongs to the host, which is the only layer that knows it.
