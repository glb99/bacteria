# Dialogue 05 — What building it taught the model

> Opened 2026-08-24, after ADR 0006's phase one shipped in `bacteria` and started writing rows from real conversations. Seven merged PRs: schema, engine, repository, service, identity, extraction, the deferred job, and a read-only HTTP surface.
>
> Dialogues 01 and 03 were reasoning. Dialogue 04 was a prototype. This is the first pass where the model met a database, a driver, a live model provider and a real transcript — and **six of these were found by something failing, not by anyone thinking harder.**
>
> Split deliberately: §A are corrections to things `MENTAL-MODEL.md` currently states wrongly, which want confirming and promoting. §B are questions implementation raised that only the human can settle.

## A. Corrections

### A1 — The open sentinel is `datetime.max`, not an infinity value

§3 says a bound is "stored as an infinity sentinel for open and a null for unknown". Postgres accepts `'infinity'::timestamptz` happily and **psycopg 3 refuses to read it back** — `DataError: timestamp too large (after year 10K)`. It does not degrade to `datetime.max`; it raises.

A row carrying it would be writable, correct in SQL, and fatal to every Python caller that selected it — invisible until the first open-ended fact was read, which is the first time anyone says "she *is* their CTO".

`datetime.max` was checked against the real stack instead: round-trips exactly, compares greater than `now()`, orders correctly. The cost is that a fact genuinely valid until the year 9999 is indistinguishable from an open one, which every query treats identically anyway.

**The general lesson is the one worth promoting**: "use a sentinel at the extreme of the type" is a design that depends on the *driver*, not only on the database, and no amount of reasoning about Postgres would have found this.

### A2 — Evidence cannot cite a constraint

Dialogue 04's E1 record says the succession inference cites "both assertions and the constraint", and ADR 0006 was drafted the same way. The schema forbids it: evidence is a foreign key to the assertion log, and **a constraint has no row to point at**.

Evidence is assertion ids only; the constraint is named in the conclusion's statement. If constraints ever become assertions — which R6's "contestable hypothesis" framing suggests they eventually should — that is where the third id goes.

### A3 — Idempotence is implemented, not implied

§3's append-only design plus a deterministic assertion id looks like it gives idempotence for free: the same claim recorded twice is the same row. It does not. **An identical primary key raises rather than being ignored**, so a retried job crashed instead of landing where it had.

It works now because `record` explicitly ignores conflicts on the primary key. Worth stating in the model because the same reasoning error is available anywhere else "writing the same thing twice is harmless" is assumed.

### A4 — A revision is *when* an explanation becomes possible

E1 established that a conflict becomes *explained* rather than cleared. The implementation ran that inference only on observation, and had revision merely report — which is backwards, and a test of week 4 caught it: learning that a role ended in February is exactly what gives the successor a boundary to have started at.

Both paths now share one step. §5's constraint-driven inference should say that revision triggers it, not only observation.

### A5 — "An observation is not an identity" makes cheap identity safe

This looked like a blocking dependency: every assertion names two nodes, a node id can never be rewritten, so entity resolution must be solved before anything can be written down.

It isn't, and §3 already contains the reason without drawing the conclusion. Because identity is separate from observation and nodes are **linked rather than merged**, minting a node per distinct name is wrong only in the sense that one person may end up with several — nothing has to be undone. A later `same-as` assertion links them and both keep their observations.

The asymmetry is what makes it safe, and belongs in §3 explicitly:

> **Splitting one person across two nodes is recoverable. Collapsing two people into one node is not** — their assertions are already interleaved under one id with nothing recording which was whose.

So matching is exact on a normalized name and refuses to guess. A future change that makes resolution cleverer should make that test *fail*, not quietly pass more often.

### A6 — A personal graph must contain the person, and nothing says so

The model never mentions the graph's owner as an entity. Transcripts almost never name the speaker — people say "I", "me", "my team" — so the extractor invented a label, and invented a different one on the next run: `user`, `me`, `I`. The person whose graph it is became several unconnected nodes.

The owner now has a reserved node whose **id is derived from the user id rather than allocated**, so two concurrent first mentions cannot produce two of them. Its label starts as `self` and stays correctable, which is exactly why the id does not depend on it.

## B. Questions for you

### B1 — The trust tiers are inert in practice

R3 gated auto-commit on provenance: the user's own utterance may influence ranking, third-party content may not. Implementation attributes trust **per transcript slice**, because a claim cannot be reliably traced to one turn.

After the first turn, essentially every slice contains an assistant message. So `trust = "user"` almost never fires, and the tier never does anything. The first real row proved it:

```
 subject | rel | object | ends |    trust    |  status
---------+-----+--------+------+-------------+----------
 self    | pet | Canija | open | third-party | believed
```

Nothing is exposed — R3 was explicit that the tiers are an optimization and the **reserved floor** is the defence. But an optimization that never fires is complexity that reads as load-bearing.

Three ways out: accept it and document that `user` is rare; attribute per claim by asking the model which turn it came from (a thing a model can be *asked* and cannot be *held to*); or extract per user message with surrounding turns as context, which is structural but costs more calls.

**Question**: keep the tier and make it work, or drop it and let the floor be the whole story?

### B2 — F2 was answered by implementation rather than by us

Dialogue 02's F2 asked when staleness re-derivation runs: eagerly, lazily, or batched. The implementation runs it **eagerly and synchronously**, inside the revision that caused it — because the evidence walk is a single indexed query and there was no reason to defer it.

That was a decision made by writing code, not by deciding. It is probably right, and it is not what F2 imagined: the expensive re-derivation F2 worried about was re-running an LLM to redraw the conclusion, which is a different operation that still does not exist. Marking a belief stale is cheap; *replacing* it is not.

**Question**: confirm eager staleness marking, with re-derivation left unbuilt and separate?

### B3 — `prompt_version` has no home

R2 said a bad extractor run is fixed by retracting everything carrying one prompt version. That is only possible if the version was recorded at the time, and it currently lives in an `attrs` JSON blob rather than a column — the wrong home for the one field every retraction query would filter on.

**Question**: promote it to a column now, or wait until someone actually needs to run that query?

### B4 — Do we adopt the article's vocabulary, and record explicit-vs-inferred?

[Analysis 10](../analysis/10-agent-stack-memory.md) maps our layers onto the taxonomy in the reference bacteria's agent package was designed against. Three things came out of it.

**The names are better than ours** — session history, prompt context, retrieval, memory — and ours already match them. But calling the graph "memory" inside a codebase that uses *memory* for keyed entries is a collision we have tripped over twice in conversation alone.

**The two-store split is justified on a better criterion than we had been using.** Not trust, and not lifecycle: *two irreconcilable conflict policies*. Memory overwrites by key because the model must not be handed two current answers; assertions flag and keep both because a contradictory world has to be representable. Those cannot share a table. It also gives a rule for where new content goes — **can two of these be true at once?**

**And it names a decision we make implicitly and cannot inspect.** A memory layer must distinguish *explicit instruction* from *inferred preference*. Ours does — by which table a row lands in — and neither row records it. `source` says who proposed, not whether anyone meant it; `trust` says which channel a claim arrived through, not whether it was stated.

**Question**: adopt the vocabulary and state the mapping once in `MENTAL-MODEL.md`, and make explicit-vs-inferred a recorded field rather than an implication of storage?

> **Partly overtaken by [dialogue 06](06-one-memory-or-two.md).** That asks whether there should be two stores at all. If the answer is the ledger-plus-projection shape, "which table a row is in" stops being how explicit-vs-inferred is encoded, and this question becomes a field on an assertion rather than a change to two schemas. Settle 06 first.

### B5 — Retention, which is now the largest hole

The same article lists freshness, expiry and "who can inspect/delete" as constitutive of a memory layer rather than as polish. **We have none of them, in either store.**

It is worse for the graph, and the reason is ours: R2 made the assertion log durable and thereby removed the mitigation ADR 0002 had been leaning on — "being derived means it can be rebuilt smaller once a retention rule exists, which is a mitigation and not an answer." We took the mitigation away and never replaced it.

There is now a route to *see* a personal graph and no route, chore or policy by which anything ever leaves it. Its failure mode 6 is the sharp version: assertions are auto-committed, so nothing was ever deliberately chosen to be kept.

**Question**: does retention get designed now, or does it stay parked with the reason written down?

---

## Answers & agreed conclusions

_Every question here was settled by later work rather than in this file, which is why it sat open. Recorded 2026-08-28 so a dialogue whose answers live elsewhere stops reading as an open one — the same failure as a `Not built:` block describing something that is now built._

**B1 — the trust tiers are inert. Kept, and the floor is the whole story.**
Settled by not moving. `trust` still records the channel a claim arrived through and still reads `third-party` on nearly every row, and the tier was deliberately *removed from the claim display* on those grounds — a label that never varies is a word a reader must learn in order to discover it means nothing. What became load-bearing instead is `origin`: **did anybody mean this**, which is what [ADR 0011](../../adr/0011-a-confirmed-fact-may-be-spoken.md) gates speech on and what the console renders as two voices. The question asked whether to make the tier work or drop it; the answer was that a different field was doing the job.

**B2 — eager staleness confirmed, re-derivation still unbuilt.**
Confirmed by use rather than by argument. The walk is a single indexed query and runs inside the revision that causes it; nothing has wanted it deferred. Re-derivation — re-running a model to redraw a stale conclusion — remains a different operation that does not exist.

**B3 — `prompt_version` stays in `attrs`, and the query it was for got a better key.**
Half-answered by [dialogue 08's Q2](08-the-schema-is-ahead-of-the-writer.md): `session_id` is now recorded, so *what did this conversation teach the graph* is answerable and *retract everything one bad run wrote* has a filter that is a column and an index. `prompt_version` moves the day somebody runs the version query, which is still the right trigger and still has not happened.

**B4 — the vocabulary was adopted; explicit-versus-inferred became a field.**
`origin` is exactly the explicit/inferred distinction this question asked for, and it is a column rather than an implication of which table a row is in. The naming collision the question worried about resolved itself: the graph is *the graph*, keyed entries are *memory*, and [dialogue 06](06-one-memory-or-two.md) then asked whether both should exist at all.

**B5 — retention got designed, three dialogues later.**
[Dialogue 12](12-nothing-ever-leaves.md) answers it. The finding that mattered was not a removal route but that **the design had been reading append-only as a promise that rows are immortal** — a rule about how belief is *revised*, mistaken for one about lifetime. That is now [§2 principle 8](../../architecture/memory-graph.md). The first thing that actually removes anything, the expiring tail, ships from that record.

---

**What this dialogue was for.** Six of its findings came from something failing rather than from anyone thinking harder, and that held for everything after it: the tally counting an endorsement twice, the store crashing on its first turn, the sweep offering a confirmed claim. **The repository has been a more reliable witness than the record of it**, every time the two disagreed.
