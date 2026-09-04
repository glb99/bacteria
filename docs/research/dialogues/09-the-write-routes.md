# Dialogue 09 — You can see it is wrong and cannot say so

> Opened 2026-08-25, after ADR 0007 shipped and a real conversation exercised the whole engine for the first time. Extraction, catalogue, canonicalization, dates, constraint, inference, explained conflict — every layer, on real data.
>
> And nothing can be corrected. The graph now holds a contradiction about the owner's mother, a person node duplicating the owner, and a junk relation, and there is no route by which any of it changes. **The read surface got built and the write surface did not**, which is the gap [§8](../../architecture/memory-graph.md) calls the differentiating layer and the one no source builds.

## Why it is opening now rather than in its turn

This is the fourth dialogue to end by pointing at it.

- [B5](05-what-building-it-taught.md) — nothing ever leaves the graph, and R2 removed the mitigation ADR 0002 had been leaning on.
- [07's Q1](07-relation-vocabulary.md) — the tail is visible so that a person can judge it, and no one can act on the judgement.
- [07's Q3](07-relation-vocabulary.md), answered by building it — a name-claim is *dropped* because "rename the owner node" is a write path and none exists.
- [08's Q4](08-the-schema-is-ahead-of-the-writer.md) — `same_as` has no writer, so a split identity is permanent.

A question that four separate lines of work defer to is not a later question. It is the one holding them.

## What the live graph is asking for

Six rows from one conversation. Three of them want a person's decision and cannot get one.

```
self   —mother→        claudia      ⚠ CONFLICT with the next row
self   —mother→        elena        ⚠
self   —acquaintance→  Guillermo    tail; and Guillermo *is* the owner
Acme   —cto→           Diane        until 2026-02-01
Acme   —cto→           Marta        explained by an inferred succession
self   —employer→      Acme
```

Read as acts, that is the whole minimum surface:

| the person wants to say | what it touches |
|---|---|
| "elena is wrong" | retract an assertion |
| "I am Guillermo" | rename a node |
| "that Guillermo node is me" | link or merge two nodes |
| "`acquaintance` is junk" | retract, and maybe refuse the relation |
| "Marta did not start then" | reject a conclusion |

Five acts. Four of them have no mechanism at all, and the fifth — `revise` — exists but nothing calls it from outside a test.

## What the model already says, and what it does not

§8 is unusually specific for something unbuilt, and three of its rules constrain this directly.

**The user's writes are never blocked.** A constraint violation opens a negotiation — *your rule says one mother, this says two; fix the fact or fix the rule?* — rather than a refusal. So these routes validate shape and never adjudicate content.

**Rejection is recorded as a fact, not a deletion.** Confirming a merge appends `sameAs`; rejecting appends `distinctFrom`. The reason is operational: a rejection that merely deletes leaves the same similarity re-proposing the same merge forever. That generalizes past merges — *"elena is not my mother"* is a claim about the world, and a route that only closes `recorded_until` throws it away.

**Review is ambient, never modal**, and ratification is risk-weighted. Identity-level and destructive changes stage; additive low-stakes facts auto-commit. So the surface is a queue and a set of affordances rather than a modal prompt, and the thing to design against is a review everyone clicks through.

What §8 does *not* settle is the shape of the act itself, which is Q1.

## Questions

### Q1 — Is a retraction a closed row, or a new claim?

ADR 0006 built `supersede`, which closes belief in a claim and states a corrected one. Its docstring names the gap: **retraction without replacement — "that was never true" — is a sibling and is not written.**

Two shapes, and they are not equivalent.

**Close it.** `recorded_until` is set, the claim leaves the projection, the log still holds what was once believed. Minimal, uses the one field 0006 permits to change, and says nothing about why.

**Assert against it.** The rejection is itself an assertion — the `distinctFrom` move applied to any claim. The graph then records that the owner *denies* elena is their mother, which is a fact about their world, survives a re-extraction that would otherwise propose it again, and can be cited as evidence.

The second is clearly richer and it needs something the schema has not got: a claim whose object is another *claim*, since `src` and `dst` are node ids. [ADR 0008](../../adr/0008-preferences-are-assertions.md) hit the same wall from the other side and answered it by appending a same-triple assertion with a different `origin`, rather than by pointing at a row.

**Question**: does a retraction close a row, or state a denial — and if the latter, what does a denial point at?

### Q2 — Where does a rename live, when nodes have no history?

"I am Guillermo" should rename the owner node. [A6](05-what-building-it-taught.md) reserved that node's id *precisely so* its label stays correctable, and nothing corrects it.

But `graph_node` has `first_seen` and `last_seen` and no time axes. A rename is a plain `UPDATE` over a row with no record that it ever said anything else — in a package whose entire argument is that overwriting loses what a log keeps. The console would show `Guillermo` and no way to learn it was ever `self`.

Three ways: accept the mutation and say so; give nodes the same two axes assertions have, which is a real schema change for a table that is mostly a lookup; or make the label an assertion like any other and let `graph_node.label` become a projection — which is [ADR 0008](../../adr/0008-preferences-are-assertions.md)'s move exactly, one table over.

**Question**: is a label a column or a projection?

### Q3 — What is the unit, and does it need to be a thing?

§8 says *"a branch is just a set of actions not yet applied"*, and stakes both approval staging and hypothetical staging on that one mechanism. That is a strong claim about the shape of a write: an **action** is a named, validated, recordable change, and a route is only a way to submit one.

Building five endpoints instead is faster and forecloses it. Building actions first is the design's own answer and is speculative generality unless something needs it soon.

The honest test is whether anything *does*. Approval staging is wanted for exactly the acts above, since merges and retractions are the ones §8 says must stage.

**Question**: five routes now, or an action type now?

### Q4 — Is rejecting a conclusion different from retracting an assertion?

`graph_conclusion` already has a mutable `status` — `active`, `stale`, `retracted` — and `set_status` to move it. So this one is nearly built: rejecting the Marta succession is a status change, and [06's](06-one-memory-or-two.md) machinery already returns a `possible` conflict once the explanation is withdrawn.

Which makes the asymmetry worth naming rather than inheriting silently. A conclusion is a *derived belief* and may be re-derived, so mutating its status loses nothing. An assertion is a record of what was claimed, so mutating it loses the claim. **Two tables, two policies, and the reason is not which is more important but which one is allowed to be recomputed.**

**Question**: confirm that rejecting a conclusion stays a status change, and that the difference from Q1 is recomputability rather than convenience?

### Q5 — Which surface, given the console is read-only and the CLI already reviews

`GET /graph` renders; `bacteria-admin` already holds a review flow for memory proposals, with `accept-proposal` and `reject-proposal`.

So there is a precedent for a person deciding things at a terminal, and a half-built precedent for deciding them in a browser. §8 wants ambient review — *a queue inside the graph, pending changes drawn as ghosted diffs, acceptable in bulk* — which is a console feature and not a CLI one.

**Question**: do the routes land as HTTP with the console following, or as CLI commands first because the review flow already lives there?

---

## Answers & agreed conclusions

**Agreed 2026-08-25**, question by question.

### Q1 — A retraction closes belief. It does not become a claim.

The two acts sit on **different axes**, and the design already has both. *"The extractor got that wrong"* is a statement about belief — recorded time, `recorded_until`. *"elena is not my mother"* is a statement about the world — valid time, and that is **negation**, which the graph cannot represent at all.

Resolving the `mother` conflict is the first. Conflating them would make every correction of an extractor error read as a claim about a person.

**[§8](../../architecture/memory-graph.md)'s rule is already satisfied.** *"Rejection is recorded as a fact, not a deletion"* — an append-only log that closes rather than deletes is exactly that. §8's argument is aimed at merge proposals, where the same similarity re-fires deterministically forever; an assertion only returns if someone says it again, and then re-asserting is correct.

**The alternative fails mechanically.** A denial must point at a claim, and `src`/`dst` are node ids. Putting an assertion id in `dst` makes one column mean two things depending on `rel` — the failure [07](07-relation-vocabulary.md) fixed in `sentence` and [08](../../adr/0008-preferences-are-assertions.md) rejected for `trust`. A `graph_retraction` table is a second kind of thing evidence cannot cite, which 0008 rejected on structural grounds. And 0008's same-triple-different-`origin` move conflates *who said it* with *whether it is true*.

**What to add instead**: `recorded_until` is a bare timestamp, so nothing distinguishes *superseded by a correction* from *retracted as wrong* — both merely set it, and inferring the difference from whether a same-triple assertion appeared at the same instant is fragile. One small field naming the act that closed belief makes the rejection a recorded fact rather than an absence, and costs a column rather than a concept.

Actor is not recorded: in a personal graph only the owner may retract. Stated rather than left implied.

**Deferred**: general negation. A positive *"elena is not my mother"* survives re-extraction and can be cited as evidence, and §8's `distinctFrom` is one instance of it. It is a schema-level addition and must not ride in on a retraction route.

### Q2 — A label is a column; the *name* is an assertion

The question dissolves once two things it conflates come apart. **The label** is a display name — what to draw, mutable, no history needed. **The name** is a fact about the world, bi-temporal and contestable like any other.

The objection that renaming overwrites, in a package built on not overwriting, only bites if the label is where the fact lives. It is not, so overwriting a display string loses nothing.

**And this closes a loop rather than opening one.** [07's §9](07-relation-vocabulary.md) drops name-claims because `self —name→ Guillermo` made "Guillermo" a *person node* — which is how the owner became two people. Its "not built" says the fact needs somewhere to go and there is nowhere. **ADR 0008 builds the somewhere**: a name is a property, `self —name→ value:Guillermo`, functional, one slot. No new mechanism; a record already drafted.

**The hazard, sharp enough to constrain sequencing.** Renaming the owner node to `Guillermo` while a separate `Guillermo` person node exists gives two nodes with the same normalized label and kind — and `node_named` matches on exactly that pair, so resolution becomes arbitrary. [A5](05-what-building-it-taught.md) says that is the unrecoverable direction. **Rename and link cannot ship independently**: either the rename refuses a colliding label, or it lands with linking.

**Rejected**: two time axes on `graph_node`. It is the lookup table `refer_to` hits on every claim, `kind` and `attrs` do not want history, and the need belongs one table over.

### Q3 — Verbs in the service layer; routes and actions both sit on top

"Five routes *or* an action type" is a false choice, because both are wrappers. The work is the verbs — `retract`, `rename`, `link`, `reject_conclusion`, beside the existing `revise`, which has never been called from outside a test. Build those well and nothing is foreclosed.

**Why the action type does not earn its place yet**, despite §8 asking for it. §8 stakes actions on staging and names what stages: merges, retractions, type changes, edits to constraints. All five acts are on that list — but §8's other rule is that **the user's writes are never blocked**, and a person retracting their own claim *is* the approver. The acts being built now are precisely the ones that do not stage.

**So the trigger is concrete rather than "later": the first proposal a person did not originate** — entity resolution's medium-confidence band proposing a merge. Until then an action type is a dataclass with no queue, no validator registry and nothing to hold. When it arrives, it wraps verbs that already exist and are already tested.

**The one thing hard to retrofit**: these functions must return an `Outcome` rather than raise, matching `observe` and `revise`. A retraction that stales three conclusions has to say so, and a route that rediscovered it by re-querying would be a second implementation of the staleness walk.

### Q4 — A status change, and rejecting one today does not stick

Confirmed on the mechanism: `status`, `set_status` and `_explained`'s `active` check all exist, with a passing test that withdrawing the assumption returns the pair to *possible*.

**The asymmetry belongs in the record.** A conclusion is a derived belief and may be recomputed, so mutating its status loses nothing. An assertion is a record of what was claimed, so mutating it loses the claim. Two tables, two policies, and the criterion is **recomputability, not importance**.

**But that recomputability is a live hole.** After rejecting the Marta succession: `_explained` returns false, the `cto` conflict returns to *possible*, the next extraction touching `cto` runs `_reconcile`, sees a *possible* conflict, and **records a new active conclusion**. The rejection is undone by the next thing said about Acme, silently.

This is exactly §8's predicted failure — *"a rejection that merely deletes leaves the same similarity re-proposing the same merge forever"* — already in the code, one table from where §8 was looking. `_reconcile`'s docstring claims idempotence from skipping non-*possible* conflicts; retraction is what makes them possible again.

**The fix is cheap and the query is already right**: `depending_on` has no status filter, so the retracted conclusion is already in hand. Skip inference when any conclusion, whatever its status, already covers this pair with this `derived_by`.

**Which qualifies Q1.** This is the second place a rejection must be *remembered* rather than merely applied, and closing a row was enough there only because nothing re-proposes an assertion. Something does re-propose a conclusion.

### Q5 — HTTP, with the console following

Answered inside Q3. §8 wants ambient review — *a queue inside the graph, pending changes as ghosted diffs* — which is a console feature. The CLI review flow is the right home for **proposals**, and these are not proposals; they are the owner's own acts. The affordance belongs next to the thing it acts on, and the console already renders both the graph and the conflicts.

---

## What building it taught

> ADR 0009 shipped 2026-08-25 — four verbs, four routes, one column, and the console affordances behind them. Every finding below is about *verification*, not about the graph, and they arrived in a run of five defects that a person clicking found and nothing else did.

### D1 — Present and enabled is not reachable

The reported failure was that after picking `same as` there was no way to click the other node. There was. Every button was in the DOM, enabled, correctly labelled, and every assertion written against it passed.

`.graph` is a grid of `minmax(15rem, 1fr)` columns and each rendered section became one cell — so a list of *every node* was crammed into 240px. Labels wrapped to a character per line, `A c m e`, and the buttons sat crushed against the right edge.

**A DOM assertion cannot see this, and four of them in a row did not.** The state was correct; the page was unusable. What settled it in seconds was a screenshot, which was available for several rounds before it occurred to anyone to take one.

The general form is worth keeping because it is not about CSS: **the properties a test can name are not the properties a person experiences.** Presence, enablement and text are proxies chosen because they are easy to assert. Reachability — is this thing big enough, in view, not overlapped — is the thing that was actually broken, and it needed a different kind of check.

### D2 — An assertion that holds for the wrong reason, three times

Within one record's implementation the same mistake was made three times, each time caught only by deliberately breaking the code and watching the test *not* fail:

- the succession guard's first test passed unfixed, because adding a third claim made the inference decline for an unrelated reason;
- the link check asserted a `same_as` claim *existed*, which was already true from an earlier run, so the click under test did nothing and it still passed;
- rewritten to count rows, it then failed whenever the pair was already linked — because restating a believed claim is correctly not written again.

The shape is one thing each time: **asserting a state that something else could have produced, rather than the effect of the act under test.** The version that holds asserts the request happened and was accepted.

This is the same error as [Q3a](08-the-schema-is-ahead-of-the-writer.md)'s, one level up. There, a guard consulted the model's own output; here, a test consulted a state the system had many ways to reach. Both are checks that cannot distinguish *the thing worked* from *the thing was already so*.

### D3 — A destructive test has to bring its own subject

The browser checks ran against real data and retracted whichever claim came first. Across a handful of runs they removed **eight assertions**, including both `cto` claims — the pair a succession was resting on — and one of the two `mother` claims that had been the worked example for conflicts.

The graph the project had been reasoning about for two days was consumed by its own test suite, quietly, one run at a time.

There is no route that creates an assertion, so the checks cannot seed a graph of their own; they now stop at the moment of the write. That is a real loss of coverage and the right trade, and it names a gap worth recording: **the write surface can retract and link but cannot state**, so nothing outside extraction can put a claim into the graph. A seeding route is not only a test convenience — it is the thing that would let a person say something the extractor never heard.

### D4 — The delivery path is part of the system

Several rounds were spent debugging a defect that had already been fixed, because the entry point was served with an etag and **no `Cache-Control`**. A response with no such header is heuristically cacheable, and asset names are content hashes, so a stale entry point pins a browser to a build that no longer exists — the page loads, runs old code, and reports nothing.

The symptom is distinctive and was misread every time: *"your fix changed nothing."* That sentence is evidence about **delivery** at least as often as about the fix, and it was treated as a fresh bug on each repetition.

---

## Answers still open

**Q1's deferred half** — negation, so that *"elena is not my mother"* can be a fact rather than the absence of one.

**A route that states a claim**, per D3.

**Retention**, unchanged and now sharper: retracted rows accumulate exactly like believed ones, and the graph has begun to contain things a person explicitly rejected.
