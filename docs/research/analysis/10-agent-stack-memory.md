# Analysis 10 — The Agent Stack, Part 5: a concordance

> Source: [`sources/10-agent-stack-memory/`](../sources/10-agent-stack-memory/). Written 2026-08-24, after ADR 0006's phase one shipped.
>
> This note exists to do one thing: **line the article's abstractions up against ours** and say, for each, whether we have it, what we call it, and where the two disagree. The value is not the summary — it is the column that says *absent*.

## Why the mapping is worth making

The article is not another design to borrow from. It is a **taxonomy**, and we have been arguing about a boundary it already has names for: the question "should memories and the graph be separate?" is, in its vocabulary, "is the graph memory, or retrieval?"

It also matters that bacteria read this **before** designing its memory layer. Where its ADRs and our model agree, this article is a plausible common ancestor rather than a coincidence — which changes what the agreement is evidence *of*.

---

## 1. The four things it insists are distinct

Its central move. "The model only ever sees the request payload, never the full system state."

| Article | Ours | Match |
|---|---|---|
| **Session history** — the durable chronological record, *source material* | `chat_transcript_item` | exact |
| **Prompt context / working set** — the derived subset sent this turn | what `assemble_context` returns | exact |
| **Retrieval** — brings external *candidate evidence* into the turn | the ADR 0024 supplier | **designed, unbuilt** |
| **Memory** — durable state persisted outside the model and deliberately re-injected | `chat_memory_entry`, `chat_user_memory_entry` | exact |

> "Prompt context is derived state. Session history is source material."

That is §3's three layers — transcript, assertion log, projection — reached independently and stated more crisply. Its corollary, *"compaction should mean 'don't send all of this right now,' never 'erase the only record'"*, is the same argument R2 makes about what may be dropped and rebuilt.

**And there is a fifth thing in our system that its taxonomy has no row for.** The graph is not session history, not prompt context, not retrieval (nothing retrieves over it yet), and not memory by its definition — because memory is defined as *deliberately re-injected*, and the graph is never injected at all. See §5.

## 2. What a memory layer must decide

The article's list of obligations, against ours. This is the useful table.

| Obligation | Ours | State |
|---|---|---|
| What is worth extracting | `chat/extraction.py`, `graph/extraction.py` | **two** of them, §6 |
| **Explicit instruction vs. inferred preference** | — | **absent as a distinction**, §4 |
| Scope (user / session / project / tenant) | `MemoryScope`; graph keyed by `user_id` | present, narrower |
| Source | `source`, `prompt_version`, `trust`, `session_id`, `run_id` | present, richer than asked |
| Conflict resolution against older memories | overwrite-by-key · contradiction flagging | present, **two policies**, §3 |
| Freshness / expiry | — | **absent**, §7 |
| Who can inspect / delete | review routes; `GET /graph` | partial — no delete |
| Where it re-enters context | `assemble_context`; graph re-enters nowhere | present / n/a |

Six of eight, one absent, one absent-and-load-bearing.

## 3. Two conflict policies, and why that justifies two stores

The article treats "conflict resolution against older memories" as one obligation. We have two answers, and the difference is not an inconsistency:

- **Memory entries overwrite by key.** One slot per key, deliberately — the model must not be handed two answers with no indication which is current.
- **Assertions flag and keep both.** §8's flag-don't-reject: a world that is genuinely contradictory has to be representable.

Those are incompatible in one table, which is the strongest argument for the split that does not appeal to trust or lifecycle. It also says *which* store a new kind of content belongs in: **can two of these be true at once?** If yes, it is an assertion.

## 4. The distinction we do not represent, and it is the one that matters

> A memory layer must decide … **explicit instruction vs. inferred preference**

This is the axis actually separating our two stores, and **neither store records which side it is on.**

A `chat_memory_entry` is explicit *by the time it exists*, because a human activated it — but the entry itself does not say whether the human wrote it or merely approved an extractor's guess. `source` records who *proposed*, which is close and not the same.

An assertion is inferred, always, and has no way to be explicit: there is no path for a person to state a claim directly. `trust` is about the *channel* a claim arrived through, not about whether anyone meant it.

So the article names a decision our design makes implicitly, by which table a row lands in, and cannot inspect afterwards. That is a weaker position than it looks: it means "did the user actually say this?" is answerable only by reading the transcript.

## 5. Is the graph memory or retrieval?

The question that prompted this note, in the article's own terms.

**Its definition of memory excludes the graph.** "Memory brings durable state back into that turn" — the graph is never re-injected. Under its taxonomy the graph is an index, and its failure mode 5 is *"vector database as memory"*: an index helps you find records and cannot decide whether an old preference still applies.

**But the graph is not the index that failure mode describes.** That warning is about a store that has *only* similarity — no extraction policy, no conflict handling, no provenance, no TTL, no deletion, no audit. Ours has provenance, bi-temporality, contradiction, staleness and retraction. It is a memory layer that happens to be graph-shaped, and the one thing it lacks from that list is TTL (§7).

So the honest answer is that **the article's taxonomy has four slots and we built five things**, and the fifth — a durable, governed, contradictory model of the world that never speaks — is the thing `MENTAL-MODEL.md` §1 argues memory should have been all along.

Where the two genuinely disagree: the article assumes memory's purpose is re-injection, so a store that is never injected is not memory. Our §1 assumes memory's purpose is *modelling reality*, and injection is one consumer among several. **That is a real disagreement about what memory is for**, not a terminology clash, and it is worth keeping visible rather than resolving by choosing vocabulary.

## 6. Two extractors, and what the article says about that

Both of ours are background jobs, which the article endorses — memory maintenance belongs off the hot path, and *"blocking every turn on memory maintenance is why agents feel smart in a notebook and sluggish in production."*

What it does not endorse is two of them. Failure mode 6, **implicit memory writes**, is *"persisting something just because the model/tool/user said it once, without deliberate lifecycle decision."* Assertions are auto-committed: nobody decides, per claim, that this is worth keeping.

Our defence is that assertions never reach a prompt, so the influence channel failure mode 9 describes stays closed. The article's warning is broader than that — it is about durable state, not prompt-visible state — and on its terms we are accumulating rows nobody chose to keep and nothing will ever remove. §7.

## 7. The gap this note found: freshness, expiry, deletion

The article lists these as constitutive of a memory layer, not as polish. We have **none of them**, in either store.

It is worse for the graph than for memory entries, and the reason is recorded: R2 made the assertion log durable, which removed the mitigation ADR 0002 had been relying on — *"being derived means it can be rebuilt smaller once a retention rule exists, which is a mitigation and not an answer."* We took the mitigation away and did not replace it.

The article also connects this to a right we have not implemented: *"who can inspect/delete."* A person can now **see** their graph, and there is no route, chore or policy by which anything ever leaves it.

## 8. Where it independently confirms decisions we already made

Worth recording, because agreement reached from a different direction is evidence rather than an echo.

| Article | Ours |
|---|---|
| "Retrieval solves access. Memory solves ownership." | ADR 0024, *"an index ranks; it does not speak"* |
| Retrieved evidence must carry source, version, freshness, permissions, reason, confidence, provenance | §3's provenance on every assertion; PROV-O |
| A similarity score means "looks related", not "should govern the answer" | §6's conclusions carry confidence and evidence, and are not authority |
| Failure mode 9: memory poisoning is a **trust boundary** | §9's trust; ADR 0016/0017; R3's reserved floor |
| Failure mode 4: missing scope → "personalization becomes leakage" | ownership in the key, not a filter — R6 |
| "Audit the assembled working set — what the runtime put in front of it" | `run_meta`, ADR 0019; `considered` in ADR 0024 |

## Open questions for the human

1. **Do we adopt the article's vocabulary?** Calling the graph *memory* while the codebase it lives in uses *memory* for keyed entries is a collision we have already tripped over twice in conversation. Options: rename ours, adopt theirs, or state the mapping once in `MENTAL-MODEL.md` and let both stand.
2. **Should explicit-vs-inferred become a recorded field** rather than an implication of which table a row is in?
3. **Retention.** Parked in R2, listed here as constitutive. It is now the largest hole in the design, and the one a person is most likely to ask about first.

## Provisional conclusions

- The four-way taxonomy is worth adopting as vocabulary; our layers already match it and the names are better than ours.
- The two-store split is **justified on the article's own criterion** — two irreconcilable conflict policies — which is a stronger argument than the trust one we had been using.
- The graph is a fifth thing its taxonomy lacks a name for, and that is the interesting result rather than a failure of the mapping.
- **Retention is the gap.** Everything else the article requires, we have in some form.
