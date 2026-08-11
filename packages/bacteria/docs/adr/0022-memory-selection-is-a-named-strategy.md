# 0022 — Memory selection is a named strategy that reports what it passed over

## Status

Accepted — 2026-08-11

## Context

Which memories reach the model was a slice expression inside `_format_memory`:
sort by `created_at`, keep the last twenty. That is a policy with several
defensible answers — recency, relevance to the incoming message, scope
precedence, some combination — expressed as a line of code that cannot be
substituted, named, or reported on.

The sharper problem is what it hid. Assembly reported `memories_included` and
nothing else, so a turn that showed twenty of twenty and one that showed twenty
of two hundred produced identical evidence. Every entry past the bound stopped
reaching the model with nothing anywhere recording that it had — and each one
was a fact the owner deliberately preserved, which is a worse loss than an old
message dropping out of the window.

That is the same unreportable loss [ADR 0010](0010-bounded-context-window.md)
refused when it declined summarization, and the reason
[assembly](../../src/bacteria/context/assembly.py) still declines relevance
ranking. It was present in memory the whole time. Nobody had noticed because the
bound was documented, and a documented rule reads like a reported one.

[ADR 0021](0021-memory-is-scoped-to-a-session-or-a-user.md) made it worse
without changing it: two scopes now merge before the bound applies, and session
entries are newer by construction, so twenty facts from one conversation can
push out a standing preference the owner set deliberately.

## Decision

Selection moves to `bacteria/context/retrieval.py` behind a `RetrievesMemory`
protocol, with `RecentMemory` as the default implementing exactly the previous
behaviour. Assembly keeps rendering and bounds; it no longer decides *which*.

**The return type carries `considered`, not just the chosen set.** This is the
part worth the change. `considered - len(chosen)` is the number of memories the
owner kept and the model was not shown, and it reaches the transcript as
`memories_considered` in `run_meta` alongside `retrieval_strategy`. A strategy
now has to say what it passed over in order to answer at all.

**Scope precedence stays in assembly.** Session-over-user is collapsed before a
strategy is called, so every strategy inherits the rule rather than
re-implementing it. Two implementations that each re-derive a policy are two
implementations that will eventually disagree about it — the failure the
conformance suite exists to catch, better prevented than detected. The cost is
real and stated in the module: a strategy cannot use scope as a ranking signal,
so "standing preferences outrank conversational ones" is not expressible without
moving precedence in.

**Synchronous, and candidates are passed in.** A strategy ranks what it is
given. An implementation needing to `await` is querying a store, which is a
different design — a data-access layer, living in the host next to the
repository — and pretending one abstraction serves both would hide the part that
actually costs something. That migration also changes what `get_state` is for,
since it currently promises the whole memory set.

**No `score` field yet.** It is what an embedding strategy would fill and
nothing reads it today; adding it now would be a field with no reader, which
this project treats as a defect wherever it finds one.

## Consequences

Behaviour is unchanged. Every existing assembly test passed without
modification, which is what a refactor should look like; the only test that
needed editing asserts `run_meta`'s exact payload.

A dropped memory is now visible in three places: on `AssembledContext`, in the
transcript through `run_meta`, and therefore to the evaluation checks, which can
be pointed at it once there is a policy to assert.

There is deliberately no eval check for it yet. "How many dropped memories are
acceptable" is a lifecycle policy nobody has chosen, and writing a check that
encodes one would settle that question by accident — the same mistake ADR 0020
avoided with retention. The data exists so the decision can be made against real
runs rather than against a guess.

Replacing recency is now a substitution rather than an edit, which is what makes
a ranked retriever something that can be evaluated against the runs the current
one produced instead of something that has to be trusted.

The seam adds a module and an indirection for one implementation. That is
justified by the reporting, not by the substitutability: if `considered` were
not worth recording, inlining the rule would still be the right call.
