# 0009 — The graph is correctable

## Status

Proposed — 2026-08-25.

Completes what [ADR 0006](0006-the-memory-graph-is-an-assertion-log.md) built one half of. Its read surface shipped; the write surface did not, and four separate pieces of work have since deferred to it.

Requires a migration — one column on `graph_assertion`. Independent of [ADR 0008](0008-preferences-are-assertions.md): they touch the same table and neither depends on the other's decisions.

## Context

0006's engine ran end to end against a real conversation for the first time, and every layer worked: extraction, vocabulary, canonicalization, dates, constraint evaluation, a defeasible inference, an explained conflict. Six rows.

**And nothing about them can be corrected.**

```
self   —mother→        claudia      ⚠ conflict with the row below
self   —mother→        elena        ⚠
self   —acquaintance→  Guillermo    unratified; and Guillermo *is* the owner
Acme   —cto→           Diane        until 2026-02-01
Acme   —cto→           Marta        explained by an inferred succession
self   —employer→      Acme
```

A person can see, in their own console, that the system holds two mothers for them and a second copy of themselves. They have no way to say so. `GET /graph` renders; nothing writes.

Read as acts, those six rows ask for five things, of which **four have no mechanism** and the fifth is never called:

| the owner wants to say | verb |
|---|---|
| "elena is wrong" | retract |
| "I am Guillermo" | rename |
| "that Guillermo node is me" | link |
| "`acquaintance` is junk" | retract |
| "Marta did not start then" | reject a conclusion |

This record is opening now rather than in turn because it is the fourth thing to point here. 0006 left retention open with nothing leaving the graph; 0007 made the unratified tail visible so a person could judge it, and gave them no way to act on the judgement; 0007's §9 *drops* a name-claim because renaming the owner node is a write path that does not exist; and `same_as` has no writer, so a split identity is permanent. A question four lines of work defer to is the one holding them.

## Decision

### 1. Retraction closes belief. It does not become a claim.

`retract(assertion)` sets `recorded_until`. The row stays, `state_at` still reconstructs the belief held before the correction, and nothing is deleted.

**Closing and denying sit on different axes and only one is being built.** *"The extractor got that wrong"* is a statement about **belief** — recorded time. *"elena is not my mother"* is a statement about **the world** — valid time, and that is negation, which this schema cannot represent. Resolving a conflict between two extracted claims is the first, and conflating them would make every correction of an extractor error read as a claim about a person.

**The design's rule is already satisfied.** *Rejection is recorded as a fact, not a deletion* — which an append-only log that closes rather than deletes is. That rule's own argument is about merge proposals, where a similarity computation re-fires deterministically forever; an assertion only returns if someone says it again, and then re-asserting is correct. §4 is where the rule does bite.

### 2. One column says which act closed belief

`closed_by`: `superseded` or `retracted`, null while believed.

`recorded_until` is a bare timestamp today, so a correction and a rejection are indistinguishable after the fact — recoverable only by checking whether a same-triple assertion appeared at the same instant, which is fragile and would silently stop working the moment anything else writes at that instant. The distinction is what makes a rejection a recorded fact rather than an absence, and it costs a column rather than a concept.

**No actor column.** In a personal graph the only thing that may retract is the owner, and a column that can only hold one value records nothing. Stated here so that it is a decision rather than an omission; it changes when a graph has more than one writer.

### 3. A label is a column; a name is an assertion

`rename(node, label)` is an `UPDATE`. No history, and none is lost.

**Two things were being conflated.** A **label** is a display name — what to draw on a node. A **name** is a fact about the world, and belongs in the log like any other fact, bi-temporal and contestable. The objection that renaming overwrites, in a package whose argument is that overwriting loses what a log keeps, only holds if the label is where the fact lives. It is not.

0007's §9 drops name-claims because `self —name→ Guillermo` made "Guillermo" a *person node*, and says the fact needs somewhere to go that does not exist. **0008 is that somewhere** — a name is a property, `self —name→ value:Guillermo`. This record does not build it and does not need to.

**Rejected**: two time axes on `graph_node`. It is the lookup table `refer_to` hits on every claim, so making it temporal puts a time filter on every resolution, and `kind` and `attrs` do not want history either.

### 4. Rejecting a conclusion is a status change, and is remembered

`reject(conclusion)` calls the existing `set_status(retracted)`. Nothing new.

**The asymmetry with §1, stated so it is not inherited silently**: a conclusion is a *derived belief and may be recomputed*, so mutating its status loses nothing — the log still holds what it was derived from. An assertion is a *record of what was claimed*, so mutating it loses the claim. Two tables, two policies, and the criterion is **recomputability, not importance**.

**And the recomputability is a hole that has to be closed in the same change.** Today, rejecting the succession sets its status, `_explained` stops matching, the conflict returns to *possible*, and the next extraction touching that relation sees a *possible* conflict and **records a fresh active conclusion**. The rejection is undone by the next thing the owner says about Acme, silently.

That is the re-proposal failure the design predicts for merges, already present one table away from where it was expected. `_reconcile`'s claim that idempotence comes from skipping non-*possible* conflicts does not survive a retraction, because retraction is exactly what makes a conflict possible again.

So: **inference skips a pair that any conclusion already covers, whatever that conclusion's status.** `depending_on` has no status filter, so the retracted row is already in hand and the fix is a condition rather than a query.

### 5. The verbs live in the service layer; routes are thin

`retract`, `rename`, `link` and `reject` join `observe` and `revise` in `graph/service.py`, and return an `Outcome` rather than raising — the same shape, for the same reason: a retraction that stales three conclusions has to say so, and a route rediscovering that by re-querying would be a second implementation of the staleness walk.

**Not an action type, and the trigger for building one is named.** The design wants actions first-class — *a branch is just a set of actions not yet applied* — and stakes both approval and hypothetical staging on it. What stages is *merges, retractions, type changes, edits to constraints*, which is this list. But its other rule is that **the owner's writes are never blocked**, and a person retracting their own claim is the approver rather than the applicant. The acts here are precisely the ones that do not stage.

An action type earns its place at **the first proposal a person did not originate** — entity resolution's medium-confidence band proposing a merge, which is unbuilt. Until then it is a dataclass with no queue, no validator registry and nothing to hold. When it arrives it wraps verbs that already exist and are tested.

### 6. HTTP, with the console following

`POST` routes beside `GET /graph`. The CLI's review flow stays where it is: it is the right home for *proposals*, and these are not proposals.

The design wants review to be **ambient rather than modal** — a queue inside the graph, pending changes drawn as ghosted diffs, acceptable in bulk — which is a console feature. The affordance belongs beside the thing it acts on, and the console already renders both the graph and its conflicts.

### 7. Rename and link ship together

Renaming the owner node to `Guillermo` while a separate `Guillermo` person node exists produces two nodes with the same normalized label and the same kind — and `node_named` matches on exactly that pair, so which one a later mention resolves to becomes arbitrary.

0006's asymmetry is the reason this is not a detail: splitting one person across two nodes is recoverable, and collapsing two people into one is not. A rename that manufactures an ambiguous lookup is a step toward the unrecoverable direction.

So `rename` **refuses a label that collides with another node of the same kind**, and `link` is what resolves the collision. The refusal is a message telling the owner the two are probably the same thing, which is the negotiation this surface exists to have.

## Consequences

**A migration, and a small one.** One nullable column, no backfill of meaning: every existing row is `closed_by = NULL`, which is what "still believed" already meant.

**The graph becomes correctable and therefore wrong more visibly.** A person who can retract will retract, and the rows they leave behind — closed, with `closed_by = 'retracted'` — are a record of the extractor's error rate that nothing currently produces. That is worth having and nothing reads it yet.

**Retention is still open**, and this makes its absence sharper rather than better: retracted rows accumulate exactly like believed ones, and "nothing ever leaves the graph" is now true of things the owner has explicitly rejected.

**`link` is asserted, not applied.** It writes a `same_as` assertion and does not merge nodes, per 0006's identity rule. Two nodes remain, joined by a claim, and every consumer decides what to do about it. Nothing in the read surface does anything with it yet, so the first version links and nothing visibly changes — which is correct and will look like a bug.

### The one to dislike

**This spends a schema change and a route surface on a graph that still cannot tell the agent anything.** Retrieval is unbuilt, so the honest description is that it makes a viewer editable before establishing that the thing being viewed is worth keeping — and 0006's kill criterion is still unanswerable.

The defence is that correctness is a precondition for the criterion rather than a reward for passing it: a graph nobody can fix accumulates errors at exactly the rate the extractor makes them, and judging retrieval over uncorrected data measures the extractor rather than the design.

## Alternatives rejected

**Retraction as a denial assertion** — the claim's rejection recorded as a fact pointing at it. Richer, and it needs a claim whose object is another *claim*, which the schema cannot hold. Every way of forcing it in has been rejected elsewhere for a reason that still applies: an assertion id in `dst` makes one column mean two things depending on `rel`, which 0007 fixed in `sentence` and 0008 refused for `trust`; a separate table is a second kind of thing evidence cannot cite, which 0008 rejected on structural grounds; and 0008's same-triple-different-`origin` move conflates who said a thing with whether it is true.

**A `deleted` flag or an actual delete.** Both discard what was believed and when, which is the property the second time axis exists for, and both make a past run unreplayable — the exact failure 0006 was written to prevent.

**CLI commands first**, reusing the review flow. Faster, and it puts the affordance somewhere other than beside the thing it acts on. The review flow is for proposals a person adjudicates; these are the owner's own edits.

## Not built

**Negation.** *"elena is not my mother"* as a positive fact — it survives re-extraction, can be cited as evidence, and `distinctFrom` is one instance of it. A schema-level addition that must not ride in on a retraction route.

**Bulk anything.** One act, one call. The design wants bulk acceptance of ghosted diffs and that is a console affordance over a queue that does not exist yet.

**Undo.** A retraction can be re-asserted by stating the claim again, which is not the same thing and will be noticed.
