# 0024 — Memory candidates are supplied by the host, not read whole from state

## Status

Proposed — 2026-08-14

Extends [ADR 0022](0022-memory-selection-is-a-named-strategy.md) rather than
superseding it. `RetrievesMemory` keeps its shape, its default, and its job;
this record adds the stage in front of it that 0022 named and declined to build.

## Context

[ADR 0022](0022-memory-selection-is-a-named-strategy.md) put memory selection
behind a protocol and wrote down, in the same breath, the thing it was not
doing:

> An implementation needing to `await` is querying a store, which is a different
> design — a data-access layer, living in the host next to the repository — and
> pretending one abstraction serves both would hide the part that actually costs
> something. That migration also changes what `get_state` is for, since it
> currently promises the whole memory set.

That migration is now wanted. The host is building an index over memory — a
graph extracted from the transcript, with vector similarity over its nodes — and
the question this record answers is what shape of it reaches this package.

Today the whole path assumes the candidate set is small enough to hold.
`get_state` returns every memory entry, `assemble_context` merges the two scopes,
and a synchronous strategy ranks what it is handed. That is correct while memory
is a few dozen keyed facts. It has no answer at all when the thing that knows
which memories are relevant is an index, because the candidate set is then the
result of a query rather than a field on a dataclass.

There is a second, smaller problem, and it is one 0022 created. The seam it built
cannot currently be used. `Runtime.run_turn` calls `assemble_context(state,
user_text)` with two arguments; `window_size`, `memory_limit` and `retriever` all
take defaults, and `RecentMemory()` is constructed inline at the call. So this
package declares a protocol for substituting memory selection and offers no way
to substitute it. A record that made substitution the point should have carried
the wiring, and did not.

The constraint that shapes everything below is the one
[ADR 0014](0014-async-at-the-io-boundaries.md) set: `async def` means "this
reaches outside the process", and the pure layers stay synchronous. Assembly is a
pure layer. Whatever fetches candidates cannot be inside it.

## Decision

Selection becomes two stages with different natures: **narrow, then rank.**
Narrowing is asynchronous, does I/O, and belongs to the host. Ranking stays
synchronous, pure, and here.

**A second protocol, `SuppliesMemoryCandidates`, declared here and implemented by
the host.** One method, `async def candidates(...)`, taking the session, the
incoming message, and a bound; returning the entries worth ranking. It sits
beside `SessionRepository` in the set of things a host provides, for the reason
0022 gave — this is a data-access layer, and data access is the host's half of
the arrangement.

**The runtime awaits it; assembly never does.** The supplier is called in
`Runtime.run_turn`, before `assemble_context`, and its result is passed in as an
argument. Assembly keeps its synchronous signature and its purity. Putting the
await inside assembly would make the one function that answers "what was the
model shown" also a function that talks to a database, and that function's value
is that it can be read in one sitting.

**The return type carries `considered`, and carries the two scopes separately.**
Two things ride on this:

- `considered` is the ADR 0022 invariant and it does not survive by accident. A
  supplier that queried two hundred rows and returned twelve must say two
  hundred, or a memory the owner preserved stops reaching the model with nothing
  recording that it had — the exact loss 0022 exists to have made visible. When a
  supplier runs, its count is what reaches `run_meta`.
- The scopes stay separate because precedence is assembly's policy and 0022
  refused to let it be re-derived. A supplier that merged them would be deciding
  that session beats user, in the host, where a second host would decide it
  again and eventually differently. So the supplier returns what it found in each
  scope, `_merge_scopes` collapses them here as it does today, and the strategy
  is still handed one set.

**A supplier returns `MemoryEntry` values and nothing else, and that is the
security boundary rather than a typing convenience.** Everything the model is
shown must have passed through `remember` or `activate` — through a human, by
[ADR 0017](0017-memory-is-proposed-and-confirmed.md). A supplier that could
return arbitrary text would let a retriever put content into the system prompt
that nobody confirmed, which is precisely the escalation 0017 prevents, arriving
through a component that looks like plumbing rather than like a write. An index
may decide *which* confirmed facts are surfaced. It may not contribute a fact.

Put as a rule, because the type only enforces it here and the temptation will
arrive elsewhere: **an index ranks; it does not speak.**

**Retrieved external evidence stays unbuilt, deliberately.** The `Not built:`
block in `bacteria.agent.context.assembly` describes the other thing — documents
and passages arriving as an *additional section*, marked as candidate evidence
rather than authority. That is a different decision with a different hazard, and
folding it in here is how the index would acquire a voice as a side effect of
gaining a query. It gets its own record when someone wants it.

**Absent a supplier, nothing changes.** The parameter is optional, the default is
`None`, and assembly then reads `state.memory` and `state.user_memory` exactly as
it does now. A host that never supplies one sees identical behaviour, which is
what makes this additive to every existing implementor.

## Consequences

The seam 0022 built becomes usable. `Runtime` grows configuration for the
retriever as well as the supplier, so "which rule ran" stops being answerable
only as "the default, because nothing can pass another".

**A protocol count of two, and a question a new host now has to answer.**
`SessionRepository` was the whole of what a host provides. Implementing one
protocol and not the other is now a legitimate state, and "do I need a supplier"
has no answer in the type system — the honest answer is "only if your memory is
too large to rank in memory", which is a judgement about data rather than about
code.

**`considered` now means two things.** Without a supplier it is how many entries
exist; with one it is how many the query examined. Those are different questions
with one name, and a number whose meaning depends on configuration is worse than
one that does not. The mitigation is that `run_meta` records the supplier
alongside `retrieval_strategy`, per
[ADR 0019](0019-a-run-records-how-it-was-configured.md), so a past run says which
reading applies to it. The mitigation is real and it is not the same as the
problem not existing.

**Two bounds now exist and nothing coordinates them.** The supplier takes a
limit and so does the strategy. A supplier returning fewer entries than
`memory_limit` makes the ranking decorative; one returning far more makes the
strategy the real bound and the supplier's limit cosmetic. Neither is wrong and
nothing anywhere reconciles them.

### The one to dislike

**This reintroduces the failure `assemble_context` refused.** That module
declined relevance ranking for a stated reason: it makes a memory's absence
*silent and query-dependent*, so the same turn phrased differently surfaces a
different set, and a fact the owner deliberately preserved can vanish with
nothing reporting it. A supplier is that failure, arriving one layer earlier and
with a database behind it. Nothing in this record removes the objection. What it
does is insist the loss is counted — `considered` is the whole of the defence,
and "we know how many we dropped" is a weaker answer than "we did not drop any".

Whoever builds a supplier still owes an answer to the question that module
asked and this one does not close: *what happens to a preserved fact that did not
score well.* "It was not relevant" remains something the owner who wrote it
cannot check.

**No eval check for it, on purpose.** How many dropped candidates are acceptable
is a policy nobody has chosen, and a check encoding one would settle it by
accident — the same reason 0022 and
[ADR 0020](0020-deterministic-evals-over-recorded-runs.md) both left it alone.
The data exists so the decision can be made against real runs.

## Alternatives rejected

**Make `RetrievesMemory` async.** One protocol, one concept, no second thing to
implement. It also makes every existing strategy a coroutine that never awaits,
puts an I/O boundary inside a pure layer against ADR 0014, and erases the
distinction that matters — that ranking is an algorithm anyone can test with a
dict, and narrowing is a query against a store. 0022 called this out by name and
was right.

**Let the supplier merge scopes and return one set.** Simpler signature, one less
concept in the return type. It moves precedence into the host, where the next
host re-derives it, which is the disagreement the conformance suite exists to
catch and this package prefers to prevent.

**Have `get_state` take a query.** Keeps one protocol and one method. It also
turns the store's "here is everything about this session" contract into "here is
what I thought you wanted", which every caller that is not assembly would then
have to know about — the review surfaces, the transcript route, the conformance
suite. The store's promise is worth more intact.

**Let the supplier return passages as well as entries.** It is what a general
retriever wants and it would arrive with the graph rather than after it. It also
hands unconfirmed text a path into the system prompt, which is ADR 0017 undone by
a component nobody would think to review as a write path. If it is wanted, it is
wanted as a separate section with its own record and its own marking — not as a
widened return type on this one.
