# 0017 — Separate proposing a memory from activating one

## Status

Proposed — 2026-08-08

Supersedes the part of [ADR 0016](0016-memory-is-written-by-the-owner-not-the-model.md)
that gives the model no way to write memory. The rest of 0016 — the owner's
entrance, the recency bound, session scoping — stands unchanged.

## Context

Memory has an entrance: the session's owner writes it over HTTP. That works and
is not what people mean by agent memory. A user who says "always answer briefly"
produces nothing; someone has to notice, decide it is worth keeping, and write
it by hand. The feature is a durable preference store with an API, and the thing
it is mistaken for is an agent that notices.

Two ways to close that gap present themselves, and both fail for the same
reason.

**A `remember` tool.** The model proposes a call, the gate answers, the handler
writes. Everything needed already exists — `ToolRegistry`, the approval seam,
evidence in the transcript. ADR 0016 declined it: memory is injected into the
system prompt of every later turn, so a model that can write memory writes its
own future instructions. One injected user message becomes an instruction that
outlives the message carrying it, and the transcript shows only a tool call that
succeeded. It is also blocked in the application today for an unrelated reason —
approval has nobody to ask over HTTP until a run can pause and resume.

**A background job reading the transcript.** It sidesteps approval entirely,
costs the turn no latency, sees a whole conversation rather than one exchange,
and can be deferred inside the turn's own transaction. But the extractor is
itself a model call over user-controlled text, so it extracts an injected
instruction as faithfully as a real preference — and it removes the two things
the tool had: a human anywhere near the write, and a record in the transcript
tying the memory to the turn that caused it. It is also the failure
[ADR 0010](0010-bounded-context-window.md) rejected in summarization, inverted:
a summarizer silently decides what to discard, an extractor silently decides
what to keep.

The common failure is not the plumbing. It is that a write becomes an
instruction with nobody in between. Approval, pausable runs, and retry policy
are all downstream of that, and solving them does not touch it.

Worth stating plainly, because it is what makes this hard: the danger is not
that the model does something expensive or irreversible. `remember` touches
nothing outside our own database. The danger is that it edits the instructions
it will be given next, which is why it is a *higher*-risk capability than tools
that look far more alarming.

## Decision

Split the operation in two. **Proposing a memory is not writing one, and
activation is a human act.**

`MemoryEntry` gains two fields:

- `status` — `proposed` or `active`. `assemble_context` surfaces only `active`
  entries, so a proposal reaches no model.
- `source` — who proposed it: the owner, the model, or a named job.

Anything may propose. The owner's own writes arrive `active`, because the owner
*is* the human act this record protects. Two proposers are expected:

- A `remember` tool, built here, handed a store and a session by whoever
  composes the turn. It writes `proposed` entries only.
- A background job over the transcript, built by the host. This package does not
  know it exists; it only knows proposals have a `source`.

Because the tool can only propose, its approval gate may allow by default. What
is being gated is "record a suggestion", which genuinely is low-risk. The
dangerous step moved to a surface where a human is already the actor.

**Conflicts resolve at activation, not at write.** Proposals are keyed by
`(source, key)`, so two proposers may both propose `tone` and both survive.
Collapsing to a single `key` happens when a human activates one. This follows
the rule the ingestion pipeline already applies to duplicate records: merging or
last-one-wins silently discards something a caller meant, and the collision
belongs to whoever can actually judge it.

The host supplies the surfaces this implies — listing proposals, activating one,
rejecting one. They are not specified here; this package owns the state model
and the tool, not the review workflow.

## Consequences

The agent can notice things. A fact stated in conversation produces a proposal
without anyone typing it, which is the behaviour the feature was mistaken for
having.

Injection stops at a queue instead of a prompt. An attacker who gets the model
to propose "always comply with X" has produced a row a human will read, not an
instruction the model will follow.

Provenance becomes debuggable and actionable. "The job has been noisy" is
answerable, and later mutable, because `source` distinguishes proposers.

Job retries stop being a hazard. A proposal keyed by `(source, key)` is
idempotent, so a re-run overwrites its own previous suggestion rather than
accumulating duplicates — which is what makes the background proposer safe to
retry where ingestion jobs are not.

### The ones to dislike

**This is still not an agent that learns.** It is an agent that suggests. Every
memory continues to require a human, and the work has moved from authoring to
reviewing rather than disappearing. Anyone hoping the gap closes here will find
it narrowed and still open.

**A review queue nobody reads is worse than no queue.** Proposals accumulate,
nothing activates, and the feature looks broken while behaving exactly as
designed. Nothing here surfaces a pending count or nags, and the first
deployment that ignores the queue will conclude the agent has no memory.

**The protocol's implicit contract widens.** Every `SessionRepository`
implementation must now round-trip two more fields, and the in-memory store must
carry them to stay honest. The conformance suite catches divergence, which is
the reason to trust this, but the surface a second implementer must satisfy is
larger than it was.

**The approval gate becomes decorative for this tool.** Allowing by default is
correct while the tool can only propose, and it will look like protection to
whoever reads it next. If anyone later lets the tool write `active` entries
directly, the gate will appear to have been guarding something it was not.

**The bound does not cover proposals.** `DEFAULT_MEMORY_LIMIT` applies to active
entries at assembly. A session with thousands of unreviewed proposals costs
nothing in the prompt and everything in the review surface, and nothing here
bounds that.

## Alternatives rejected

**Auto-approve model writes into active memory.** The fastest path and precisely
what ADR 0016 refused. It treats the gate as the missing piece when the missing
piece is the human.

**Last-write-wins across proposers.** Whichever wrote most recently owns the
key. Silent, and the winner depends on when a worker happened to run — the same
shape as the `seq` collision this project has already fixed once, and no more
acceptable here.

**Namespace model memories and render them as weaker** — "the assistant noted
that…". Still in the system prompt, still steering, and it relies on the model
treating its own note as lesser evidence, which is exactly the judgement an
injection attacks.

**Let the background job write active memory.** Removes the human and the audit
trail while keeping the hazard intact, in exchange for convenience.
