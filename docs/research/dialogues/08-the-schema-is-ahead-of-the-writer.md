# Dialogue 08 — The schema is ahead of the writer

> Opened 2026-08-25, from the same testing pass as [dialogue 07](07-relation-vocabulary.md) and scoped out of it deliberately: 07 governs the predicate, these four do not touch it.
>
> They share a shape. Every one is a capability ADR 0006 **decided** and phase one did not fill in — three columns that exist, are documented, are indexed, and are never written; and one decision, *identity is linked and never merged*, with no writer at all. Nothing here is a wrong design. It is a design that shipped with its writer producing the minimum that made rows appear.
>
> **Q1 and Q2 were already fixed when this was opened**, in `bacteria`'s `9746064`, and both are recorded below as answered rather than deleted — the reasoning stands and one of them was decided against the way this leaned. The questions were drawn from live rows, every one of which was written before that commit; **a database is a record of what the writer used to do**, and reading it as the current state is the mistake to carry forward.
>
> **All four are now settled**, every one of them by implementation rather than by discussion. The dialogue read the repository more slowly than the repository wrote itself. What it was worth is the two places its reasoning was wrong — Q1's false analogy, and Q3's assumption that a date must be complete.

## Q1 — A re-mention writes a new believed row

`self —parent→ mom` exists three times — 16:03:38, 16:04:55, 16:12:42 — all with `recorded_until` null, so `current()` returns three identical edges for one unchanged fact.

The mechanism is deliberate at every step. `_assertion_id` hashes the run's `now`, and its docstring gives a good reason: a random id would double-write every claim on a retried job, and the unique constraint would not catch it because it is keyed on the claim rather than on the id. `observe()` never compares against `current()`. `dropped` counts only malformed claims.

**The tempting fix is to suppress at write, and [07's Q1](07-relation-vocabulary.md) just decided against this exact shape of fix.** Canonicality is derived rather than stored because a stored classification turns a later change into an `UPDATE` across an append-only log. The parallel holds: the claim genuinely *was* made three times, and the log's job is to record claims. Dropping the second and third makes the log misreport what happened, and it discards the only signal separating a fact mentioned weekly from one mentioned once.

So the defect is likely not in the log at all, but in `current()` being read as though it were a projection. It is a filter — *everything believed* — and a projection over identical triples should collapse them and carry the count.

**The cost of doing nothing is real and compounds.** A fact mentioned weekly is fifty-two rows a year, every one believed, and [B5](05-what-building-it-taught.md) is right that nothing ever leaves the graph. Evidence walks get noisier for conclusions that cite any of them.

**Question**: collapse in the projection and keep every row, with the count becoming corroboration — or suppress at write when an identical triple is already believed over the same interval?

## Q2 — `session_id` is an omission; `run_id` is a question

Both null on all fifteen rows. `_claim()` sets neither.

**`session_id` is a plain bug.** It is in scope in `extract_assertions`, and the column's own docstring explains that it is deliberately *not* a foreign key so that it can be empty when a claim has no session — while in practice it is empty when a claim has one. The consequence is that [B3](05-what-building-it-taught.md)'s retraction story is half-built: `prompt_version` in `attrs` can answer *which wording produced this*, and nothing can answer *which conversation taught the graph this*.

**`run_id` is not a bug and may be correctly null.** In this codebase a `run_id` groups the items one agent *turn* wrote. An extraction reads a slice spanning many turns — session `9807a99f` had reached sequence 52 — so a claim drawn from that slice has no single run to name. Leaving it null is arguably honest.

The alternative is to redefine it here as the *extraction* run's id, which is what a retraction query would actually reach for: "everything that bad job wrote". That is more useful and it makes one column name mean two different things in two tables, which reads fine today and is a trap for whoever joins them later.

**Question**: fill `session_id`, and then — park `run_id` with the reason recorded, or redefine it as the extraction run?

## Q3 — No fact has a start, so succession can never fire

`valid_from` is null on all fifteen rows, and this is not the model underperforming. It was asked for `tense`, answered `current` fifteen times out of fifteen, and was right each time; `current` maps to `Interval(None, OPEN_ENDED)`. **The prompt has no field for a date at all**, so `valid_from` is null by construction and will stay null however much traffic arrives.

That makes a whole layer inert. ADR 0006's succession inference needs a boundary — [A4](05-what-building-it-taught.md) built the revision-triggers-inference path precisely so that *learning a role ended in February* gives the successor somewhere to start. Nothing in the pipeline can ever supply the February.

The cheap version is an optional `since` / `until` on the extraction schema, populated only when the transcript states one. Most turns state nothing, the fields stay null, and that is exactly the unknown state the three-state design already has a slot for.

**The trap is that a model asked for a date will supply one.** "I've worked there for years" becomes an invented 2019, and an invented start is worse than no start: it is checkable-looking and wrong. Under-claiming is the recoverable direction and the design already errs that way on purpose — `past` and `unknown` both collapse to an unknown end rather than guessing. So the instruction has to be *only when stated explicitly, never inferred*, which is precisely the kind of instruction a model can be **asked** and cannot be **held to** — [B1](05-what-building-it-taught.md)'s phrase, and the same problem.

**Question**: add explicit date extraction with a guardrail of its own, or leave the temporal machinery unexercised until a source with real dates exists — ingestion, a calendar — and accept that until then the bi-temporal design is carrying only one of its two axes?

## Q4 — Identity is linked, never merged, and nothing links

`same_as` appears nowhere in the graph package. ADR 0006 §7 decided linking over merging; [A5](05-what-building-it-taught.md) established the asymmetry that makes cheap node-minting safe — splitting is recoverable, collapsing is not — **because a later link repairs the split**. The repair has no writer.

In the rows: `mom`, `Claudia` and `elena` are three person nodes that the log cannot tell apart from three different people. `Guillermo` sits beside `self` as a fourth, though [07's Q3](07-relation-vocabulary.md) already claims that one as a rename rather than a link.

Underneath is something 07's Q3 only half-noticed: **`mom` is a role, not a name.** The extractor is told to use the name as it appears, and it did — "my mom" *is* how it appears. So role-labelled nodes are not a one-off; they will keep being minted, and each is permanently disjoint from the name it refers to.

Two separable problems, and only one is about linking. Stopping the mint is a prompt question: prefer a name when the transcript supplies one, and then what — skip the claim, or keep the role node? Linking what already exists needs a writer, and A5 says collapsing is the unrecoverable direction, so it must be either conservative to the point of near-uselessness or human-confirmed. The confirmation surface still does not exist, which is [B5](05-what-building-it-taught.md) again and [07's Q1](07-relation-vocabulary.md) again.

**Question**: is `same_as` a catalogue relation the extractor may propose, or a human-only act that waits on write routes that are not built?

## Sequencing

Q1 and Q2 are cheap and independent. Q3 is independent and is the one that unlocks a layer already built and paid for. Q4's second half depends on the write routes, which are unbuilt and which [B5](05-what-building-it-taught.md), 07's Q1 and now this all point at — **the review surface is the recurring blocker, and it has now been the answer-shaped hole in three consecutive dialogues.**

---

## Answers & agreed conclusions

### Q1 — Suppressed at write, and the projection reading was wrong

**Settled in `9746064`, against the way this dialogue leaned.** `observe()` now skips a claim the log already believes, keyed on the claim *and its valid interval*. The count of what was actually written is reported rather than assumed.

The argument that beat the projection option is one word: **a repeat is not news about the world.** The log records claims about the world, not the event of someone saying something — so a restatement is not a second claim, and writing it appends a row that says what the log already says. That is a cleaner line than the one drawn here, which treated "the claim was made three times" as a fact the log owed a record of. It is a fact about the *conversation*, and the transcript already holds it.

**Keying on `valid` as well as the triple is the part worth keeping.** "She is their CTO" and "she was their CTO until February" are the same triple over different spans; collapsing them would swallow a correction. What *should* happen there is a revision, nothing produces one from an extraction yet, so today the second lands beside the first and the constraint layer reports it.

**And it is not the shape 07's Q1 rejected.** That question was whether a *classification* — canonical or not — may be stored on a row, and the objection was that a later reclassification becomes an `UPDATE` across an append-only log. Declining to write a row at all mutates nothing. Not writing is not the same as writing a decision, and this dialogue conflated them.

### Q2 — `session_id` filled; `run_id` deliberately null

**Also settled in `9746064`, both halves the way this expected.**

`session_id` is written. It was a plain omission with the value in scope at the call site.

`run_id` stays null with the reason recorded rather than being redefined: a claim comes from a *slice*, which may span several runs, so naming one would attribute the claim to whichever ran last. That is a stronger reason than the "one column, two meanings" objection raised here — it is not that the redefinition would be confusing, it is that the value would be **wrong**.

### Q3 — Dates are extracted, and the guardrail is refusal

**Agreed 2026-08-25.** Optional `since` / `until` on the extraction schema, parsed strictly, with most of the new tests asserting a refusal rather than a parse.

**The concession that decided the format.** `YYYY`, `YYYY-MM` and `YYYY-MM-DD` are all accepted, and a partial date resolves to the first instant of the period it names. Requiring a full date looked like the disciplined choice and is not: ADR 0006's worked example is *"she left in February"*, so the strict rule would have made **the design's own canonical case unextractable**. When a model's specification and its worked example disagree, the example is the one that was checked against reality.

**The risk runs the opposite way from the defect**, which is what makes this different from every other gap in this dialogue. Q1 and Q2 were things not written down; this is a thing that will be written down *too eagerly*. A model asked for a date supplies one, and an invented start is worse than no start — a null is honestly ignorant, where `2019` is checkable-looking and wrong. So: relative dates refused rather than resolved, years outside 1900–2100 refused, an end before its start dropping both bounds rather than swapping them.

The year bound is the one worth keeping. A hallucinated `9999` collides with the open sentinel, so an invented date would become **a claim that the fact is still true** — the failure that spreads rather than sits. §3's choice of `datetime.max` for "open" has this cost and [A1](05-what-building-it-taught.md) did not see it: a sentinel at the extreme of a type is reachable by garbage.

**On "asked and not held to".** [B1](05-what-building-it-taught.md) named the pattern — an instruction a model can be given and cannot be bound by — and this is the third instance, after per-claim trust and [07's C3](07-relation-vocabulary.md) naming rule. The answer that keeps working is the same each time: **do not rely on the instruction, make the failure cheap.** Here the parser refuses what the instruction should have prevented, and a refused bound leaves the claim exactly as well off as every row written before the field existed.

**Deferred, with the reason recorded.** Relative dates need to know what *now* was for that turn, and the prompt cannot carry today's date — `PROMPT_VERSION` hashes the prompt text and would churn daily, destroying the one key retraction has. Anchoring belongs in the rendered transcript. This is the first time the version-as-hash decision has cost something.

#### Q3a — What the first real conversation did to that answer

The feature shipped and was exercised the same day. It produced five assertions, every one canonical, and one of them was this:

```
reason                              bound            stated?
"Diane left Acme in February 2026"  until 2026-02    yes
"Marta took over as CTO"            since 2026-02    no
```

Nobody said when Marta started. **The model performed a succession** — the same reasoning `infer_succession` exists to perform — having been told in the prompt not to infer dates.

**The damage is not a wrong date.** February is very likely right. The damage is *which artifact it became*. The engine performing that inference writes a conclusion: confidence 0.6, evidence on both premises, withdrawn when either moves. The extractor performing it writes an **assertion**, indistinguishable from something observed. [§2 principle 6](../../architecture/memory-graph.md) — *an assumed value never enters the log* — was discovered by a prototype and broken by a feature within a day.

**And it hid itself.** `infer_succession` requires an open claim whose start is *unknown*. Supplying the start removes the precondition, so the boundary lands as a fact and nothing ever proposes it as an assumption. The empty conclusions table looked like the inference having nothing to say; it was the inference having been pre-empted. **A guess that fills a gap also silences whatever was watching the gap.**

##### The guard that failed, and why it was never going to work

The first fix checked the bound against the claim's `reason` — the words the model gives as support. Asked again, the model returned:

```
"Marta took over as CTO [in February 2026]"
```

It wrote the date into its own justification, in brackets, and the check passed.

**A check on a model's explanation is not a check.** `reason` is produced by the same model in the same call as the thing it justifies, so this was verifying an output against its own footnote. A model that will invent a date will invent the support for it, and the iteration between those two was one run.

Checking the *transcript* instead would not have helped either, and that is the part worth keeping: the sentence was *"Diane left Acme in February 2026 and Marta took over as CTO"*. The date is genuinely there — attached to the **other clause**. Presence in the source proves nothing about which claim it belongs to.

##### The guard that holds reads arithmetic

> A claim whose `valid.start` equals another believed claim's `valid.end`, for the same subject and relation and a different object, is a succession.

Exact, mechanical, no language involved, nothing a paraphrase can reach. The start is stripped — which restores the precondition the guess had removed — and the same boundary returns as a conclusion carrying confidence and evidence.

**The accepted cost**: a genuinely stated start that happens to coincide is demoted to an assumption. Nothing can tell it from the guess, and the asymmetry decides it, in the same shape as [A5](05-what-building-it-taught.md) — an assumption recorded as a fact cannot be spotted afterwards, where a fact recorded as an assumption is visible, cited, and one confirmation from being restated.

##### The rule this generalizes to, proposed for promotion

[B1](05-what-building-it-taught.md) named the pattern *asked and not held to*: an instruction a model can be given and cannot be bound by. Four instances so far — per-claim trust, [07's naming rule](07-relation-vocabulary.md), date invention, and now succession. Each answer has been the same: do not rely on the instruction, make the failure cheap.

This one sharpens it, because the **second** attempt failed too, and it failed in a way the first did not predict:

> **A guardrail that consults the model's own output is not a guardrail.** It can only be talked around, and it will be, because the same call produces both the claim and the evidence for it. A check earns its name when it is computable from something the model did not write — the schema, the arithmetic, another row.

The catalogue's kind signature already had this property and nobody noticed it was the reason it worked. The naming denylist does too. The prose check did not, which is why it lasted one run.

**Proposed for [§2](../../architecture/memory-graph.md)**, beside principle 6, since principle 6 is what it protects.

### Q4 — `same_as` has a writer, and the extractor is deliberately not it

**Settled in `4db862c` (ADR 0009)**, which also answered the half this dialogue said was blocked: the write routes it was waiting on are the same change.

`service.py` writes the relation. The catalogue carries `same_as` with `extractable=False`, so **the vocabulary handed to the model does not contain it** — and `extraction.py` drops a proposed one rather than demoting it to the tail, on the grounds that a tail merge would still be a merge somebody guessed.

That is [A5](05-what-building-it-taught.md)'s asymmetry enforced structurally rather than remembered. Splitting one thing across two nodes is recoverable and collapsing two into one is not, so the party permitted to merge is the person and never the model. This dialogue framed the choice as *"conservative to the point of near-uselessness, or human-confirmed"*; the answer taken was neither — the relation exists and is ordinary, and only the *proposer* is restricted.

**The kind signature had to grow for it.** `src_kind` and `dst_kind` became optional, because `same_as` relates two things of whatever kind they both are and has no single pair to state. That is the first entry whose signature checks nothing, and it is admitted on functionality instead.

---

**All four questions in this dialogue were answered by implementation rather than by discussion**, and in each case the code landed before or alongside the writing. That is worth noting once rather than four times: the dialogue was a slower reader of the repository than the repository was a writer of itself. Its value was not the questions but the two places where the reasoning turned out to be wrong — [Q1](#q1--suppressed-at-write-and-the-projection-reading-was-wrong)'s false analogy to a stored classification, and Q3's assumption that a date must be complete.
