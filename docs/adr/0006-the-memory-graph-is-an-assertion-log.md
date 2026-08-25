# 0006 — The memory graph is an assertion log, not a derived index

## Status

Accepted — 2026-08-23. Phases one and two shipped; **phase three is unbuilt**.

The condition this record set for itself — Proposed until something implements
it — is met: the schema, the engine, identity, extraction, the deferred job and a
read-only HTTP surface all run against real conversations, and
[ADR 0007](0007-the-relation-vocabulary-is-a-catalogue.md) amends it from
experience. §8's retrieval — similarity resolving an anchor, traversal doing the
work — is not built, so the kill criterion in §9 cannot yet be run. *Accepted*
names the decision, not the finished state.

Five things came out of building it rather than out of arguing about it:

- **The open sentinel is `datetime.max`, not an infinity value.** Postgres accepts
  `'infinity'::timestamptz` and psycopg 3 refuses to read it back, raising rather
  than degrading — fatal to every Python caller, and invisible until the first
  open-ended fact was read. A sentinel at the extreme of a type depends on the
  *driver*, not only on the database.
- **Evidence cannot cite a constraint**, because a constraint had no row to point
  at. §6 says the rule is named in the conclusion's statement instead. ADR 0007
  dissolves it by making functionality a property of a relation.
- **Idempotence is implemented, not implied.** A deterministic assertion id does
  not make a repeated write harmless — an identical primary key raises — and a
  deterministic id collapses a *retried job*, never a fact mentioned again next
  week. Both needed writing.
- **A revision is when an explanation becomes possible**, so inference runs from
  revision as well as observation. The first version had revision merely report,
  which is backwards: learning that a role ended in February is exactly what
  gives a successor a boundary to have started at.
- **A personal graph must contain the person.** The owner needs a reserved node
  whose id is derived from the user id rather than allocated, or two concurrent
  first mentions make two of them and the graph's owner is several people.

**Amends [ADR 0002](0002-the-memory-graph-is-postgres-tables.md) rather than
superseding it.** Everything 0002 decided about *which database* stands, and that
was the bulk of it: Postgres tables rather than a graph database, pgvector,
keying by `user_id`, provenance on edges, incremental extraction from a
watermark, and the two-phase build. What changes is the shape of the rows and
which package owns them. 0002's phase one shipped. Its phase two — "nodes, edges, vectors,
traversal" — is unbuilt, and this record changes the shape of it before anything
depends on it.

Depends on the agent's ADR 0024, which decides how this reaches the agent. That
dependency is the unbuilt part: nothing supplies memory candidates from the graph
yet, which is the same gap as phase three above.

## Context

0002 was accepted on the strength of phase one and stated plainly that phase two
was "the part still taken on faith". A design pass in a separate research repo
produced a fuller model for that phase and then reconciled it against this
codebase, question by question. Most of 0002 survived. Four things did not, and
two of them are cheap now and expensive after there are edges.

The findings that force this record:

**One time axis, not two.** 0002 calls its edges bitemporal and names
`valid_from`/`valid_to`. Its stated benefit — "what did this system believe last
Tuesday stays answerable" — is a *recorded-time* question that those columns
cannot answer: filtering today's beliefs to a past valid interval returns what we
think **now** about Tuesday. Graphiti, which the record credits, carries four
timestamps. Half were taken. The same schema block already puts `first_seen` /
`last_seen` on its node table, which *are* recorded time — so one axis went on
nodes and the other on edges.

This collides with something already built. The agent's ADR 0020 runs
deterministic evals over recorded runs; evaluating a past run means reconstructing
the memory that run saw. With one axis the eval does not fail — it grades the
wrong thing.

**The key cannot hold history.** `(user_id, src, rel, dst)` is a current-state
key: one row per triple, so a relation believed, retracted and believed again
cannot be represented. Adding recorded-time columns to that table produces columns
claiming to record history in a table whose key forbids it.

**Recorded time cannot be backfilled.** Valid time can sometimes be recovered
later from testimony. The day something was learned is unrecoverable from
anything but a record made at the time — which is why 0002's own sentence,
"expensive to retrofit once there are edges", applies with more force than it was
written with.

**`[?..]` hides a choice nobody made.** An executable replay of the design's own
worked example found that every behaviour involving valid-time overlap depended
on how an unknown bound is read, and that the model had never said. Under one
reading the showcase contradiction never fires at all; under another it fires by
implicitly claiming a role reached back forever.

## Decision

### 0. It is its own feature, in `app/graph/`

0002 said the tables were "owned by `chat/` because features own their tables",
which was right when the graph was three tables derived from one feature's
transcripts. It is no longer that. This owns tables, a background task, routes,
and a lifecycle of its own, and `chat/` owns *a conversation* — a package that
owned both would be the one place in this application where "which feature is
this" had no answer.

So: `bacteria.app.graph`, and the tables are `graph_*` rather than 0002's
`memory_*`. The prefix matches `chat_*` and states the owner, which is the thing
a table name is for here. Nothing is renamed by this, because none of 0002's
tables were ever created.

The consequence to know about, because every part of it is silent: **three**
modules import every models module for the side effect of registering tables on
`SQLModel.metadata` — `migrations/env.py`, `tests/conftest.py` and
`tests/test_migrations.py` — and a new package must be added to all three. Each
omission fails differently and none of them fails loudly. Miss `env.py` and
autogenerate does not see the tables, so `just makemigration` writes nothing.
Miss `conftest.py` and the suite builds a schema without them. Miss
`test_migrations.py` and the drift test still passes, having quietly stopped
comparing them at all.

### 1. `graph_assertion` is an assertion log

```
graph_assertion
  assertion_id      PK (surrogate)
  user_id, src, rel, dst
  attrs
  valid_from, valid_to          -- three states each, see below
  recorded_at, recorded_until   -- when believed; NULL = still believed
  trust                         -- 'user' | 'third-party' | 'inferred'
  session_id, run_id            -- provenance, unchanged from 0002
  UNIQUE (user_id, src, rel, dst, recorded_at)
```

Current graph is `recorded_until IS NULL`. Belief at T is
`recorded_at <= T AND (recorded_until IS NULL OR recorded_until > T)`.

Closing `recorded_until` is an UPDATE to bookkeeping metadata, not an overwrite of
a fact; the value itself is never edited. The purist alternative — append a
tombstone row carrying a `retracts` pointer and never UPDATE — is more faithful
to the append-only claim and makes every read a self-join. Declined.

### 2. Both bounds have three states

| Value | Meaning | Phrasing that produces it |
|---|---|---|
| a timestamp | known | "she left in February" |
| `datetime.max` | **open** — has not ended, true now | "she's their CTO" |
| `NULL` | **unknown** — may or may not have ended | "she was mentioned as CTO" |

**Not `'infinity'`, and this was checked rather than assumed.** Postgres stores
`'infinity'::timestamptz` happily and **psycopg 3 refuses to read it back**:
`DataError: timestamp too large (after year 10K)`. It does not map to
`datetime.max`; it raises. Any row carrying it would be writable, queryable in
SQL, and fatal to every Python caller that selected it — a failure that would not
appear until the first open-ended fact was read.

`datetime.max` as a timezone-aware value was verified against this stack instead:
it round-trips exactly, compares greater than `now()`, and orders correctly, so
indexes and `ORDER BY` behave. `NULL` keeps its real SQL meaning, which is
*unknown*, and `NULL <= now()` correctly evaluates to unknown rather than false.

The cost of the sentinel, stated so nobody discovers it as a bug: a fact genuinely
valid until the year 9999 is indistinguishable from an open one. Every query
anyone will write treats the two identically, which is why this is acceptable and
not merely tolerable.

The alternative was a separate `valid_to_kind` column — explicit, no magic value,
and a check constraint asserting `kind = 'known'` exactly when `valid_to` is not
null. Declined for the reason `chat/models.py` gives about a different table:
that is encoding in a constraint what a value can state outright.

Open means *true as of now*, so an open-ended interval provably contains the
present moment and **two open-ended intervals definitely overlap** however unknown
their starts. That is what makes a contradiction between two current claims
decidable without pretending either claim reaches back forever.

The extractor gains one judgment: tense to open-versus-unknown. Present tense to
open is robust, and getting it wrong is recoverable, since it is an assertion like
any other.

**Not built**: bounds that are themselves intervals — "ended, but we do not know
when", which past tense states constantly. It maps to `NULL` here, which loses
conflicts that could have been decided and errs toward under-claiming.

### 3. The graph is durable; only some of it stays disposable

0002's "a migration may drop and rebuild it" no longer holds for edges. The rule
that decides membership, applicable to anything added later:

> Can it be regenerated **deterministically** from what is kept? If a
> non-deterministic model call or a human decision went into it, it is durable.

This is 0002's own criterion — "deleting a row loses a human's activation decision
that exists nowhere else" — extended to cover the second way to lose something
irrecoverably. `MemoryContent.prompt_version` already exists because someone knew
the extractor is a versioned, non-deterministic call: re-deriving yields what
*today's* extractor would say about Tuesday's transcript.

Still disposable: `graph_node_vec`, current-state materializations, derived
properties, staleness marks.

What 0002 wanted from disposability survives in a better form. A bad extractor is
still fixed by re-running: the re-run appends and closes recorded intervals, and a
month of bad output is retracted by provenance — everything carrying
`prompt_version = X` — rather than deleted. Retraction is what `chat/extraction.py`
lists under *Not built*, pointing at this record's phase two.

### 4. Conclusions are their own table, not proposals

A conclusion is a belief with mandatory evidence links to `assertion_id`s, a
confidence, prose, `derived_by`, and a lifecycle: derived → active → stale →
superseded | retracted.

It is **not** a `chat_memory_proposal`, for three reasons: that lifecycle is
terminal and has no `stale`; its `(session_id, source, key)` key overwrites
idempotently, while two conclusions about one subject are both legitimate; and it
is conversation-scoped, while a conclusion is about entities and remains a belief
in the next conversation.

**Activation emits.** Accepting a conclusion writes an ordinary
`chat_memory_entry` carrying its prose and a back-link. The agent's ADR 0024
boundary stays verbatim — the supplier returns `MemoryEntry` values and nothing
else — and `bacteria-agent` is not touched.

**Staleness demotes, never deletes.** A stale conclusion stops being supplied as a
candidate; the entry and the human's activation decision survive, and it returns
to the queue naming the evidence that went. Removing something from a projection
needs no human; deleting a human's decision does.

### 5. Two surfaces, with a reserved floor

Writing to the graph and contributing text to a prompt are different acts.

- **Graph writes are risk-weighted.** Additive, clearly-sourced facts commit
  without review.
- **Prompt text is confirmed only, always** — the agent's ADRs 0016 and 0017, and
  0002's "the graph never contributes text", unchanged.

The split has a hole: the context window is bounded (agent ADR 0010), so anything
influencing ranking can **suppress** — pushing a confirmed guardrail out of the
window without injecting a token.

> **Reserved floor.** Human-ratified memories — the user-scoped ones, where the
> agent's ADR 0021 records that a human decided the fact outlives its
> conversation — always ship regardless of ranking. Graph influence orders only
> the remainder.

This is a condition of the split, not an enhancement. Auto-commit is additionally
gated on the `trust` column: the user's own utterance may influence ranking,
third-party content may not, model inference is a conclusion. The tiers are
unreliable — users paste documents into chat, so an extractor reads
attacker-controlled text through a trusted channel — which is precisely why the
floor rather than the tiers is the defence.

**The floor is also the answer the agent's ADR 0024 asked for and could not give
itself.** That record's own objection to what it builds:

> This reintroduces the failure `assemble_context` refused… a fact the owner
> deliberately preserved can vanish with nothing reporting it… `considered` is the
> whole of the defence, and "we know how many we dropped" is a weaker answer than
> "we did not drop any".

0024 leaves that open, saying whoever builds a supplier still owes an answer to
*what happens to a preserved fact that did not score well*. This record answers
it for the class of fact it was asked about: a human-ratified memory is not
ranked, so it cannot score badly, so it cannot vanish. `considered` remains the
defence for everything else, where the loss is real and counted. That is narrower
than "we did not drop any" and it covers exactly the memories whose loss 0024
called unacceptable.

The two agree on the principle already — 0024 states it as **"an index ranks; it
does not speak"**, which is the same line drawn from the other side.

### 6. Constraint evaluation is three-valued

Satisfied, violated, or **undecidable because a bound is unknown**. Not a policy
choice: with `NULL` meaning unknown it is what the comparison returns.

Four conflict states — none, conflict, possible, **explained**. An explained
conflict is undecided with an active conclusion accounting for it, typically a
constraint-driven boundary inference: a functional constraint plus one known
boundary is real evidence about an unknown one.

Such an inference is deterministic and still **not** a derivation, because it is
*assumed* rather than *entailed* — the same data is equally consistent with a gap.
It is a conclusion with `derived_by = 'constraint-inference'`, citing both
assertions and the constraint.

> **An assumed value never enters the log.** It lives in the conclusion that
> assumed it, and readers consult that conclusion.

Writing an inferred boundary onto an assertion was tried in a prototype: the
conflict then vanished outright instead of becoming explained, the assumption
became invisible exactly where it mattered, and the next inference would have read
it as observed. Keeping it in the conclusion makes compounding structurally
impossible and leaves retraction nothing to un-write.

Guardrails: infer only when exactly one candidate has the unknown bound; the
predecessor's end must be observed rather than itself inferred; a third holder
covering the boundary blocks it.

**Test the overlap predicate.** SQL's three-valued logic is the right semantics
and a well-known footgun — `NOT IN` with nulls, aggregates skipping nulls,
`NOT (x = y)` ≠ `x <> y`. It gets a test that has been watched failing, by this
repository's existing rule for recursive CTE guards.

### 7. Identity is linked, never merged

A merge asserts `sameAs`; both observation sets survive; unmerge is a retraction.
Below the merge threshold, `possibly-same-as` is a permanent representation of
uncertainty rather than a to-do, and each consumer reads it differently: storage
keeps two, derivation computes separately per entity, rendering draws a dotted
link, and **the agent is simply told** — "Diane, possibly the same person as Diana
Mercer". A query language cannot represent that; a language model reads it and
reasons correctly, so the uncertainty is passed through rather than resolved
before it arrives.

A conclusion may cite evidence across the boundary, which makes the
`possibly-same-as` link part of its evidence — so rejecting the merge later fires
the staleness walk automatically.

Symmetric, **not transitive**: confidence does not compose. Rejection appends
`distinctFrom` rather than deleting, or the same similarity re-proposes the same
merge on every run.

### 8. Retrieval: similarity resolves the anchor, traversal does the work

A graph query must start somewhere and nothing in a raw message names the starting
node.

```
message → anchor resolution (exact identifier → lexical/alias → vector)
        → bounded traversal, mostly one hop
        → rank → candidates (ADR 0024 supplier) → assembly
```

Two distinct vector jobs. `graph_node_vec` keeps 0002's shape and does **entity
linking** over short strings — which is also what the identity confidence bands in
§7 run on. **Semantic retrieval** over assertion and conclusion prose needs its
own vectors: a node label like "Diane Mercer" embeds to almost nothing.

0002's numbers are constraints, not preferences, and carry over unchanged: 1,536
dimensions because HNSW and IVFFlat cap at 2,000; `halfvec` as the escape hatch;
`gemini-embedding-001` returns 3,072 and needs manual normalizing after Matryoshka
truncation.

### 9. Build order, and how this gets abandoned

1. **Minimum graph** — this schema, assertions written through the existing
   extraction path, one constraint construct (functional), identity links,
   evidence links, the staleness walk. No traversal, no vectors.
2. **The review surface** — the queue as ghosted diffs on a graph view: merge
   proposals, contradiction badges, bulk acceptance, evidence rendered.
3. **Retrieval** — anchor resolution, pgvector, bounded traversal, the ADR 0024
   supplier.

The order is load-bearing. Completing the substrate first would test the graph
with nothing curating it, and 0002 already calls the review queue acute and
unclosed — measuring retrieval on an uncurated graph produces a false negative on
the most expensive question here. Step 2 is not speculative spend either way,
because the queue needs fixing whether or not edges ever earn their keep.

> **Kill criterion.** If traversal-based candidate supply does not beat recency on
> the agent's ADR 0020 eval harness once the graph has had real curation, the
> graph has not earned its keep, and the fallback is 0002's own strongest rejected
> alternative: vectors over confirmed entries, no edges.

Running that honestly requires replaying past runs against the memory those runs
actually saw, which is the concrete reason `recorded_at` exists.

## Consequences

**Backups and migrations now matter.** "A migration may drop and rebuild it" stops
being true for edges and conclusions. Fixing bad data is more expensive than
deleting rows — by design, since that expense is what makes the history
trustworthy.

**The retention question reopens.** 0002 flagged it and leaned on disposability as
the mitigation: "being derived means it can be rebuilt smaller once a retention
rule exists." That mitigation is gone and nothing replaces it here.

**Tenancy isolation becomes a hard per-feature requirement.** Every graph query
must be owner-scoped, and a missing predicate is a cross-user leak rather than a
bug. `chat/access.py` already names the cost — "an ownership rule per feature,
forgotten silently, with nothing in the build to notice. Ingestion has not written
one." A graph feature keyed by `user_id` is the next place that happens.

**Visibility is not access control.** The graph lets its owner see what the agent
knows, which no permission dialog achieves, and says nothing about who else can
read the table. Operator access, backups and Logfire's instrumented psycopg spans
— which carry query parameters off the machine by design — are all invisible to
the person whose graph it is.

**More machinery before evidence.** Conclusions, constraints, three-valued
comparisons and an identity model are considerably more than 0002 planned, all of
it ahead of any signal that the graph helps.

**Autonomy and sensitivity become per-user durable state**, not configuration,
because they are human decisions.

**Two uncoordinated bounds, inherited.** The agent's ADR 0024 records that a
supplier takes a limit and so does the ranking strategy, that neither is wrong,
and that nothing reconciles them. Building the supplier makes that live: the
reserved floor consumes part of the window before ranking sees it, so the
strategy's limit is now the remainder of a budget rather than the budget. Nothing
here reconciles them either — it is named so the first person to find the ranking
decorative knows it was foreseen.

### The one to dislike

0002's own closing admission gets worse, not better. It bet that relations between
facts would start mattering and said the honest version was that "the extractor
and the proposals are the valuable half while the edges are the speculative one."
This record raises the stake: more tables, more invariants, more to get wrong,
and a durability commitment that makes a mistake expensive to walk back.

The mitigation is the ordering and the kill criterion above, and they are a real
mitigation rather than a rhetorical one — step 2 pays for itself independently,
and step 3 is where the bet is actually settled. But if the answer turns out to be
"vectors over confirmed entries", most of this was ceremony.

## Alternatives rejected

**Keep 0002's schema and add columns later.** Cheapest today and unavailable
tomorrow: recorded time cannot be backfilled, and the primary key cannot represent
a relation believed, retracted and believed again, so the migration is a key
change over a populated table rather than an ALTER.

**Treat an unknown bound as unbounded.** Simpler, one nullable column, and it
silently claims every unknown-start fact reached back forever. It also makes
"unknown" and "still true" the same value, which is the distinction the whole
temporal layer runs on.

**Adopt a memory framework** — Graphiti, Cognee, LightRAG. 0002 rejected these for
bringing their own memory model, and that reasoning is stronger now: the model is
the part that has been designed, argued and recorded.

**Build phase two as 0002 describes it, then retrofit.** This is the option that
looks pragmatic and is not. Both cheap-now-expensive-later items are schema, and
the third — the review surface — is what makes the graph worth measuring at all.
