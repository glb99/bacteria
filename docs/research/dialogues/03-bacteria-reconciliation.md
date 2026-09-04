# Dialogue 03 — Reconciling the model with bacteria

> Opened 2026-08-23, after reading the `bacteria` tree at `5a04b87`. Context and citations are in [`INTEGRATION-BACTERIA.md`](../../architecture/memory-graph.md).
>
> The finding that prompted this: bacteria's application **ADR 0002 — "the memory graph is Postgres tables"** was accepted on 2026-08-14 and already occupies the same ground as this project. Its phase one (the extractor and the proposals it writes) shipped; its **phase two — nodes, edges, vectors, traversal — is unbuilt**. `MENTAL-MODEL.md` is a much more developed design for that phase two, and arrives before anything depends on it.
>
> These seven questions are the places the two designs disagree. Unlike dialogue 01 (scope) and dialogue 02 (operational policy), these are **compatibility** questions, and several have a deadline: they change a table schema that does not exist yet and would be expensive to change once it does.

## R1 — Does recorded time go in now?

ADR 0002 calls its edges bitemporal and names one axis: `valid_from` / `valid_to`, taken from Graphiti. §3 of our model requires two — valid time *and* recorded time — and the argument is specific: without both you cannot tell a bad inference from a late discovery, which is exactly what week 4 of the worked example turns on.

ADR 0002's own sentence decides this if we accept the premise: "It costs a column pair now and is expensive to retrofit once there are edges." There are no edges yet.

The counter-argument worth hearing is that a derived index does not need to remember when it learned something, because it can be recomputed from a transcript that has timestamps. That holds only while nothing but extraction writes to the graph — and R2 is about whether that stays true.

**Question**: add recorded time to the edge schema before phase two is built?

## R2 — Is the graph derived-and-disposable, or is it the ledger?

ADR 0002 is emphatic: every row is recomputable from the transcript, the graph is not backed up separately, a migration may drop and rebuild it, and a bad extractor is fixed by re-running rather than by a data migration. That is a genuinely good property and most of why the ADR is cheap.

§3 says the opposite about the layer beneath: the append-only assertion log is the truth and current state is a projection folded from it.

These are compatible only under one arrangement — **the log is durable, the graph is the disposable projection of it**. But the moment a human ratifies, corrects, merges or retracts an assertion, that assertion is no longer recomputable from the transcript, because a decision went into it that exists nowhere else. ADR 0002 already draws precisely this line for `chat_memory_entry`: "deleting a row loses a human's activation decision that exists nowhere else."

So the question is whether assertions join `chat_memory_entry` on the durable side of that line, leaving `memory_node` / `memory_edge` disposable — which I think is right, and which preserves both documents intact.

**Question**: durable assertion log, disposable graph projection?

## R3 — Auto-commit versus "nothing unconfirmed"

§8 auto-commits additive, low-stakes, clearly-sourced facts, because the interruption budget is the scarce resource and a review everyone clicks through is worse than no review.

bacteria forbids this in three places: agent ADR 0016 (memory is written by the owner, not the model), agent ADR 0017 (proposed and confirmed), and ADR 0002's "the graph never contributes text… what it may do is decide which already activated memories are surfaced." That is a security posture, and it is the same threat §9 calls memory poisoning — bacteria's answer is simply stricter than ours.

**Proposed reconciliation**: they govern two different surfaces. Our auto-commit is a **write to the graph**. bacteria's rule is about **text reaching a model**. An auto-committed assertion may exist, be traversed, influence which memories rank highest, and be visible in the UI, while contributing no text to a prompt until a human activates it. Both rules survive untouched, and the interruption budget is spent only on things that will actually be said.

This is not what either document currently says, so it needs accepting rather than assuming.

**Question**: accept the two-surface split — graph writes are risk-weighted, prompt contributions are always confirmed?

## R4 — Where do conclusions live?

A Conclusion (§6) is derived content: a belief, in prose, with evidence links and confidence. Under "the graph never contributes text" it cannot reach a prompt at all.

The obvious home is the existing proposal queue — a conclusion becomes a `chat_memory_proposal` a human activates. That has an unexpected benefit: a proposal carrying evidence links and a confidence score is far more reviewable than the bare key/value proposals the queue holds today, which is a partial answer to the queue problem ADR 0002 flagged as acute.

The cost is that conclusions then arrive at the same rate as everything else in the queue, and §6's lifecycle (derived → active → stale → superseded) has to map onto a proposal lifecycle that only has proposed / activated / rejected.

**Question**: conclusions as evidence-carrying proposals, and does the proposal lifecycle need extending to carry `stale`?

## R5 — Does our model adopt vectors?

This is a hole on our side, not bacteria's. §5 has derivations and traversal and says nothing about similarity search. ADR 0002 committed to pgvector, 1,536 dimensions (an index cap, not a preference), and a separate `BACTERIA_EMBEDDING_PROVIDER`.

Retrieval by traversal answers "what is connected to this"; retrieval by similarity answers "what is *about* this". A memory system plausibly needs both, and ADR 0002's strongest rejected alternative was vectors with no graph at all.

**Question**: does `MENTAL-MODEL.md` gain a retrieval section, and does similarity sit beside traversal or beneath it as one more way to propose candidates?

## R6 — §9 assumed a single user, and that is now false

§9 says the enterprise apparatus "answers a multi-user problem bacteria does not have." bacteria has `user_id` everywhere, shared authentication (app ADR 0004), browser-held sessions (0005), user-scoped memory (agent ADR 0021), and ADR 0002 keys the whole graph by `user_id`.

Nothing in §9's substance is wrong — autonomy, exposure and trust are still the right three — but "one person's graph on one machine" was load-bearing for how lightly it treats them, particularly exposure.

**Question**: revise §9 for a hosted multi-user deployment, or scope our model explicitly to the single-user case and let bacteria's own auth handle the rest?

## R7 — Which half gets built first?

ADR 0002's honest closing admission: "This may not earn its keep… The graph earns its place when *relations between facts* start mattering… This record is a bet that it will, made before the evidence. The honest version is that the extractor and the proposals are the valuable half while the edges are the speculative one."

Our §1 says the opposite — that the negotiation surface, not the substrate, is the differentiator, and every substrate concept already exists in open source. Both documents nominate a different half as the speculative one.

If §1 is right, the ordering that de-risks fastest is to build enough graph to have something to negotiate over, then build the negotiation surface, rather than completing traversal and vectors first.

**Question**: does the negotiation surface come before or after phase two is complete?

---

## Answers & agreed conclusions

**(2026-08-23) R1 — Recorded time goes in now, and the change that matters is the primary key: AGREED**

ADR 0002 names the bitemporal *benefit* and implements one axis. Its own sentence — "so that … 'what did this system believe last Tuesday' stays answerable" — is a **recorded-time** question, and `valid_from`/`valid_to` cannot answer it: filtering today's beliefs to a past valid interval returns what we believe *now* about Tuesday, not what we held then. Graphiti, which the ADR credits, carries four timestamps; half were taken. The same schema block already has `first_seen`/`last_seen` on `memory_node`, which *are* recorded time — so the ADR put one axis on nodes and the other on edges.

Three arguments carried it, in order of weight:

1. **It collides with something already built.** Agent ADR 0020 runs deterministic evals over recorded runs. Evaluating a past run means reconstructing the memory that run saw, which is a recorded-time query; with one axis it silently grades today's beliefs instead. The eval does not fail — it measures the wrong thing.
2. **Provenance is not the same question.** `session_id`/`run_id` say *which run wrote an edge*. Recorded time says *which edges existed during a run*. Debugging "why did it say that" needs the second.
3. **Without both axes, "the world changed" and "we were wrong" are indistinguishable** — both appear as a `valid_to` being set. This is §3's argument and the whole of week 4 in the worked example.

**The steelman was rejected on a fact already in the codebase.** The counter-argument is that a derived index needs no recorded time because the transcript has timestamps and a watermark, so any past state can be rebuilt. But `MemoryContent` carries a `prompt_version` field: the extractor is a non-deterministic model call with a versioned prompt. Re-deriving yields *what today's extractor would say about Tuesday's transcript*, not what Tuesday's extractor said. The field exists because someone already knew that.

**The structural finding.** `memory_edge`'s key `(user_id, src, rel, dst)` is a *current-state* key: one row per triple, so a relation believed, retracted and believed again cannot be represented. Adding recorded-time columns to that table yields columns claiming to record history in a table whose key forbids it. The real question was therefore *is `memory_edge` a current-state table or a log?* — and primary keys are the most expensive thing to change once rows exist and other tables reference them.

**Agreed schema:**

```
memory_edge
  assertion_id      PK (surrogate)
  user_id, src, rel, dst
  attrs
  valid_from, valid_to          -- when true in the world; both nullable
  recorded_at, recorded_until   -- when believed; NULL = still believed
  session_id, run_id            -- provenance
  UNIQUE (user_id, src, rel, dst, recorded_at)
```

Current graph is `recorded_until IS NULL`; belief at T is `recorded_at <= T AND (recorded_until IS NULL OR recorded_until > T)`. Closing `recorded_until` is an UPDATE to bookkeeping metadata, not an overwrite of the fact — standard bitemporal practice and what SQL:2011 system-versioned tables do. The purist alternative (append a tombstone row carrying a `retracts` pointer, never UPDATE) is more faithful to §3's "facts never overwrite" but makes every read a self-join; the pragmatic form was chosen.

**Side effect: this settles [F3](02-open-gaps.md) for free.** A surrogate `assertion_id` gives evidence links an immutable row to pin to, rather than a triple whose meaning drifts. Two open questions, one schema decision.

**What decided it was the asymmetry (R1).** Adding it and never needing it costs two columns and one predicate. Skipping it and needing it costs a migration over a populated table *and a permanent hole*: valid time can sometimes be inferred later from testimony, but **recorded time cannot be backfilled at all** — the day you learned something is unrecoverable from anything but a record made at the time. §2's principle 5, and ADR 0002's own "expensive to retrofit once there are edges", point the same way. There are no edges yet.

**(2026-08-23) R2 — Durable assertion log, disposable graph projection, membership decided by a determinism test: AGREED**

**Forced by R1.** Once edges carry a `recorded_at` that cannot be backfilled, ADR 0002's disposability property is already gone for that table: a column whose entire value is that it was written at the time cannot be dropped and rebuilt. R1 made `memory_edge` durable; R2 only names what is left disposable.

The two documents agree more than they appear to. ADR 0002 says the graph is derived; §3 says current state is a projection folded from the log. **Both call the graph a projection** — they differ on what it projects *from*: the transcript, or the assertion log. That is the whole disagreement.

**Agreed: three layers, not two.**

| Layer | Contents | Durable? |
|---|---|---|
| 1. Transcript | `chat_transcript_item` — raw, append-only, already the ultimate source | yes (already) |
| 2. Assertion log | `memory_edge` with recorded time and `assertion_id`; node identity; `chat_memory_entry` / `chat_memory_proposal` with their activation decisions | **yes** |
| 3. Projection | `memory_node_vec`, current-state materializations, derived properties (§5), computed clusters, staleness marks | no — rebuild freely |

ADR 0002 collapsed layers 2 and 3, which was correct at the time: the only writer was the extractor, and the only durable human decisions lived in `chat_memory_entry`. Merges, retractions, ratification, corrections and constraints give layer 2 content that layer 1 cannot regenerate.

**The membership rule, stated once so it can be applied forever:**

> Can it be regenerated **deterministically** from what is kept? If a non-deterministic model call or a human decision went into it, it is durable.

This is ADR 0002's own criterion — "loses a human's activation decision that exists nowhere else" — applied consistently, now that LLM non-determinism is a second way to lose something irrecoverably. It does not overturn the ADR; it extends its test.

**What survives.** ADR 0002's actual *reason* for disposability was that a bad extractor is fixed by re-running rather than by a data migration. That holds, in a better form: a re-run appends new assertions and closes the recorded interval on superseded ones, and a month of bad extraction is retracted by provenance — retract everything carrying `prompt_version = X`, using a field that already exists. Retraction is exactly what `chat/extraction.py` lists under *Not built*, pointing forward to "the bitemporal edge model in the application's ADR 0002, which is phase two."

**What it costs, recorded so nobody rediscovers it as a surprise:**

- The memory graph now needs backup and migration care like any other table. "A migration may drop and rebuild it" stops being true.
- Fixing bad data becomes more expensive than deleting rows — by design, since that expense is what makes the history trustworthy.
- **Retention becomes a real open question.** ADR 0002 flagged it and leaned on disposability as the mitigation: "being derived means it can be rebuilt smaller once a retention rule exists, which is a mitigation and not an answer." That mitigation is now gone. **Parked deliberately** as bacteria's own question rather than answered here.

**(2026-08-23) R3 — Two surfaces, with a reserved floor as the load-bearing defence: AGREED**

bacteria's rule and ours were never about the same thing. Every argument in `agent/tools/memory.py` is about what the model *will be told next* — "a single injected user message … would become an instruction outliving the message that carried it, with the transcript showing only a tool call that succeeded." That is prompt-injection persistence, and §9 names the identical threat. The disagreement was only about where the gate sits.

**The split, which is bacteria's own line named rather than a new concession.** ADR 0002 already grants the graph influence over *which* activated memories surface while forbidding it any contribution to their *content*.

- **Surface A — writing to the graph**: what exists, what is traversable, what renders, what a contradiction can fire against. Governed by §8's risk-weighted ratification.
- **Surface B — contributing text to a prompt**: what the model is told. Governed by ADRs 0016/0017 — confirmed only, always.

**The attack the split does not stop, and the condition that closes it.** The context window is bounded (agent ADR 0010), so entries fall out of it. Someone able to auto-commit graph writes cannot inject text but can **suppress**: rank a confirmed guardrail such as "never send email without asking" out of the window and promote something else into the space. No injection occurs; a guardrail simply stops being said.

> **Reserved floor.** Human-ratified memories — in practice the user-scoped ones, where agent ADR 0021 records that a human decided the fact outlives its conversation — always ship, regardless of ranking. Graph influence orders only the remainder.

This is a **non-negotiable condition of the split**, not an enhancement.

**Auto-commit is gated on provenance, not only on additiveness.** §8's "clearly-sourced" needs teeth under this threat model:

| Origin | Graph write | Ranking influence | Prompt text |
|---|---|---|---|
| The user's own utterance | auto-commit | yes | only if activated |
| Third-party content (email, newsletter, fetched page, tool output) | auto-commit, **marked untrusted** | no | only if activated |
| The model's own inference | conclusion (see R4) | no | only if activated |

The worked example survives: week 3's newsletter claim about Bob Restrepo lands, fires the contradiction against `a3` and appears in the UI, while being unable to influence a single token the model sees. The honest-messy-model principle survives contact with a security rule.

**The acknowledged weakness.** "The user's own utterance" is not reliably distinguishable from third-party content, because users paste emails and documents into chat constantly, and an extractor reading a pasted block is reading attacker-controlled text through a trusted channel. No heuristic for detecting quoted material will hold. **This is why the reserved floor matters more than the tiers do**: the tiers optimize the interruption budget, the floor is the defence, and the floor holds even when source classification is wrong. If one had to be dropped, it would be the tiers.

**The payoff.** Today the queue receives everything, and ADR 0002 calls the queue problem acute. Under this rule, facts the user stated about themselves stop queueing, and what remains to review is third-party claims and the model's own inferences — which is what a human should be looking at.

**(2026-08-23) R4 — Conclusions get their own table; activation emits an ordinary memory entry; staleness demotes but never deletes: AGREED**

R3 settled the policy half (model inference: no ranking influence, no prompt text without activation). What remained was mechanical: is a Conclusion a `chat_memory_proposal`, or its own object?

**Reusing the queue was tempting** — it exists, `chat/review.py` and its HTTP and CLI surfaces are built, `propose` is the only write `extraction.py` can reach, and a proposal carrying evidence and confidence is far more reviewable than today's bare key/value.

**Three reasons it does not fit:**

1. **The lifecycle is terminal.** proposed → activated | rejected, and stops. A Conclusion goes derived → active → **stale** → superseded | retracted, and `stale` has no analogue — while staleness is the entire justification for the layer (§6: "Without that, this is an audit log; with it, the memory self-corrects").
2. **The key is wrong, in the same way R1's was.** `chat_memory_proposal`'s PK `(session_id, source, key)` is deliberately one-row-per-key so a re-run overwrites idempotently. Two different conclusions about one subject are both legitimate, and a superseded conclusion must survive rather than be overwritten.
3. **The scope is wrong.** Proposals are session-scoped and FK'd to `chat_session`. A conclusion is about entities and belongs where the graph is — user-scoped, per ADR 0002. A conclusion drawn on Tuesday is still a belief on Thursday in another conversation.

So the question posed in R4's framing — does the proposal lifecycle need extending to carry `stale`? — answers itself: **no, and that is exactly the reason to keep them separate.**

**Agreed design:**

- **Conclusions are their own table in layer 2** (durable, since an LLM call produced them and R2's determinism test puts them there), keyed like the graph — `user_id` plus a surrogate id — with mandatory evidence links to `assertion_id`s, confidence, prose, and the §6 lifecycle.
- **Activation emits; the supplier learns nothing new.** Activating a conclusion writes an ordinary `chat_memory_entry` carrying the conclusion's prose and a back-link to its id. This keeps ADR 0024's boundary verbatim — "the supplier returning `MemoryEntry` values and nothing else" — and preserves the property that **`bacteria-agent` is never touched**. Teaching the supplier to return conclusions would break that for no gain.
- **Staleness demotes, never deletes.** When evidence is retracted the conclusion goes stale and its emitted entry stops being supplied as a candidate, while the entry and the human's activation decision survive and it returns to the queue as "this went stale: `a3` was retracted."

**The asymmetry decides the direction, as in R1**: continuing to tell the model something known to rest on retracted evidence is worse than briefly not telling it something true. It also maps onto R2's layering exactly — the activation decision is durable, the supply is a projection. Removing something from a projection needs no human; deleting a human's decision does.

**Cost (R4)**: a table, a review surface that renders evidence, and a demotion path. Real work, and it is the core of the differentiator rather than scaffolding around it. Combined with R3 it shrinks ADR 0002's acute queue problem, because what reaches a human is third-party claims and evidence-bearing inferences rather than every preference the extractor noticed.

**(2026-08-23) R5 — Similarity sits beneath traversal, and there are two vector jobs, not one: AGREED**

This was a hole on our side. §5 has derivations and §11 has a generic core (`query, assert, traverse, subscribe`); neither mentions similarity. ADR 0002 had already committed to pgvector.

**The question as posed — beside or beneath? — was not a real choice.** Traversal needs an entry point: a graph query is "start at node X and expand", and nothing in a raw user message names X. Getting from text to a node *is* the problem, and that is what similarity does. Similarity is not a competing retrieval mode; it is the resolution step that makes traversal possible.

```
user message
  → anchor resolution   exact identifier → lexical/alias → vector similarity
  → traversal           bounded expansion, mostly one hop
  → rank
  → candidates          (the ADR 0024 supplier)
  → assembly            (pure; ranks what it is handed)
```

ADR 0002 supplies the evidence for the shape: roughly 85% of LightRAG's graph calls are one hop, with breadth-first traversal bounded to depth 2 and fifty nodes.

**The finding: `memory_node_vec` is sized for the wrong job.** ADR 0002 puts vectors on nodes, but a node is `"Diane Mercer"` — a name embeds to almost nothing. Meaning lives in the assertion prose and the conclusion statement. There are two distinct uses:

| Use | Input | Job |
|---|---|---|
| **Entity linking** | short strings — names, aliases | text → node id, for anchor resolution |
| **Semantic retrieval** | assertion text, conclusion prose | message → relevant beliefs |

`memory_node_vec` stays and does the first. Conclusions and assertions need vectors of their own.

**And entity linking is the machinery §8's entity-resolution bands were missing.** Exact-identifier / medium / low-but-real was designed in dialogue 01 with no implementation behind it; vector similarity over names is that implementation, `possibly-same-as` band included. One mechanism closes two open problems.

**Agreed:**

- §5 gains a **Retrieval** subsection: *traversal answers "what is connected to this", similarity answers "what is about this", and the memory needs both.*
- Two vector stores, two jobs, as above.
- **Embeddings are layer 3, disposable — and the reason matters**: not because they are cheap but because *their input is durable*. Re-embedding always yields a valid vector from text that was kept. This is R2's determinism test working correctly.
- ADR 0002's numbers are adopted **verbatim as constraints, not preferences**: 1,536 dimensions because HNSW and IVFFlat cap at 2,000; `halfvec` as the escape hatch; `gemini-embedding-001` returns 3,072 and needs **manual normalizing** after Matryoshka truncation. The last one is silent when got wrong.
- The costs are absorbed into our model too: a second vendor (an Anthropic-only deployment needs a Gemini key before retrieval works at all), and an embedding call per turn on top of the extraction call.

**One paragraph belongs in `MENTAL-MODEL.md` beside the retrieval section**: ADR 0002's strongest rejected alternative was vectors with no graph at all, and it admits that may be right. Our answer is §1 — relations between facts are the thing being asked for, and a vector index cannot represent one. That argument justifies the whole substrate and should sit where anyone questioning it will look.

**(2026-08-23) R6 — §9's three concerns survive; its single-user framing, its security claim and its scope of autonomy do not: AGREED**

**Most of §9 was right for a slightly different reason than it gave.** bacteria is multi-*tenant*, not multi-*party within one graph*: each user has their own graph keyed by `user_id`, and nothing is shared between users. Roles, marking taxonomies and policy engines therefore still stay out. Three things break.

**1. "Visibility is the security model" no longer holds.** It was true when the owner was the only viewer and the machine was theirs. Hosted, the graph lives on someone else's Postgres and visibility to the owner says nothing about who else can read the table. §9's own warning gets *worse*, not better: a graph "structured, queryable and complete across relationships, health, money and private opinion" is more dangerous on a shared server than on a laptop. Exposure now has leak paths that are not the LLM call — bacteria ships `logfire[fastapi,psycopg,google-genai]`, and **instrumented psycopg spans carry query parameters**; add operator access and backups. None of these is visible in the graph UI.

**2. Exposure needs isolation, not only gating.** Sensitivity levels on types and subgraphs still make sense, but the boundary moved from "my laptop versus the internet" to "my rows versus everyone else's in this process." A missing `WHERE user_id = ?` stops being a bug and becomes a cross-user leak. `chat/access.py` is the right shape and names the cost — "an ownership rule per feature, forgotten silently, with nothing in the build to notice. **Ingestion has not written one**" — which is a documented instance in this codebase, not a hypothetical. A graph feature keyed by `user_id` is the next place it happens.

**3. Autonomy is per-user durable state.** §9's trust dial ("a new team member gradually granted a wider purview") is per-user configuration once there are many users, and by R2's test it is a human decision, so it lives in layer 2. The same holds for sensitivity levels. Neither is a global setting or a config file.

**Agreed corrections to §9:**

- Replace "a multi-user problem bacteria does not have" with the accurate statement: one graph per user, no sharing between users, so the enterprise apparatus stays out — but **tenancy isolation is a hard requirement**, enforced per feature per ADR 0004, citing the ingestion precedent as what forgetting looks like.
- **Demote visibility to the *comprehension* model**: it is what lets a user understand what the agent knows, which no permission dialog achieves, and it is not access control. Name the non-LLM exposure paths explicitly — operator and database access, backups, telemetry.
- Autonomy and sensitivity levels become per-user, durable, layer 2.
- **§13 gains a deferral: sharing a graph between users.** That is where roles and marking taxonomies would become necessary, and it is a different product. Foreclosed deliberately rather than drifted into.

**Raised, not resolved — recorded as an open question in the model.** §9's argument for why this data is dangerous is *strengthened* by hosting it. Local-first or self-hosted answers it; hosted requires deciding the convenience is worth it. This may eventually be the deciding constraint on what bacteria is, and it is not a question this dialogue should settle by assumption.

**(2026-08-23) R7 — Minimum graph, then the negotiation surface, then complete phase two — with a kill criterion: AGREED**

The two documents nominate different halves as speculative, and they are not in conflict once lined up: extraction is **built and proven**; the substrate is **known but unproven here**; the negotiation surface is **unproven anywhere**. Three tiers, not two camps.

**The argument that decided it: completing phase two first tests the graph under conditions guaranteed to make it look bad.** Build nodes, edges, vectors and traversal before any curation surface exists and the graph fills with exactly what §10 predicts — near-duplicate types, unmerged identities, no constraints, `Person` and `Contact` and `Human` all meaning the same thing. Curation is the scarce resource and nothing would be curating, since ADR 0002 already calls the review queue acute and unaddressed. Measuring retrieval quality on *that* graph produces a **false negative on the most expensive question in the project**.

**And R3 forced it.** Under R3 the graph cannot contribute prompt text until a human activates something, so without a negotiation surface a completed phase two cannot change the agent's behaviour at all except through candidate ranking — a retrieval system whose entire output is gated behind a review nobody can perform efficiently.

**The objection does not hold.** Building the surface before knowing the graph earns its keep is not wasted effort, because the surface is the fix for a problem bacteria already has: ADR 0002 calls the queue problem acute and leaves it open, and reviewing evidence-bearing proposals in bulk is valuable with or without traversal. The work does double duty; completing phase two first does not. The worked example agrees — its only two interruptions were a merge and a type promotion, decisions that exist *only if there is a surface to make them on*.

**Agreed order:**

1. **Minimum graph** — the R1/R2 schema, assertions written through the existing extraction path, one constraint construct (functional), identity links. No traversal, no vectors.
2. **The negotiation surface** — the queue as ghosted diffs on a graph view: merge proposals, contradiction badges, bulk acceptance, evidence rendered. ADR 0002's queue fix and the differentiator, in one piece of work.
3. **Then anchor resolution, vectors and traversal** — tested against a graph a human has been curating, which is the only fair test of the bet.

**The kill criterion, committed to in advance because ADR 0002 was honest enough to state its bet:**

> If traversal-based candidate supply does not beat recency on the eval harness once the graph has had real curation, the graph has not earned its keep — and the fallback is ADR 0002's own strongest rejected alternative: vectors over confirmed entries, no edges.

It is falsifiable and the infrastructure exists: agent ADR 0020, deterministic evals over recorded runs — which is also the thing R1's recorded time was needed to make correct.

---

**All seven questions answered 2026-08-23.** As in dialogue 01, most answers were *forced* rather than chosen: R2 by R1, R4 by R3, R7 by R3. R1 and R6 were settled by asymmetries (recorded time cannot be backfilled; a hosted graph is more dangerous than a local one), and R5 dissolved on inspection — "beside or beneath" was not a real choice, because traversal has no entry point without similarity.
