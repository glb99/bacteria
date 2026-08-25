# 0011 — A confirmed fact may be spoken, through the supplier and not the keys

## Status

Proposed — 2026-08-25.

Unblocks retrieval, which unblocks [ADR 0006](0006-the-memory-graph-is-an-assertion-log.md)'s kill criterion. Requires no migration: `origin` already exists and already carries the distinction this record acts on.

## Context

The supplier seam is built. A graph-backed supplier — anchor resolution, bounded traversal, candidates — is the next piece and **cannot be written**, because there is nothing it would be allowed to return.

The agent's ADR 0024 is explicit and puts it as a rule: *an index ranks; it does not speak.* A supplier returns `MemoryEntry` values only, because everything a model is shown must have passed through a person. So a supplier selects among things already speakable; it can never make something speakable by finding it.

Under the graph, *speakable* means `origin="stated"`. And the only claims that reach `stated` are **preferences**, because `remember` refuses any key the catalogue has no preference relation for. Preferences hang off the owner node.

So: anchor resolution finds `Acme`, one hop finds `cto` and `employer`, and every one of those is `inferred` and therefore unspeakable. **A supplier written today would traverse correctly and return an empty set, every time.** Running the kill criterion against that would produce a null result and read as a verdict.

### The half of curation nobody built

0006's build order put the review surface *before* retrieval so that retrieval would be measured on a curated graph. Curation was read as **removing what is wrong** — and retract, reject, rename and link, all of [ADR 0009](0009-the-graph-is-correctable.md), do exactly that.

The half missing is **keeping what is right**. A design pass recorded it from the other end without seeing the consequence: the write surface *can retract and link but cannot state*, so nothing outside extraction can put a claim into the graph and nothing at all can promote one.

## Decision

### 1. Confirming a fact is inside ADR 0017, not an exception to it

The agent's ADR 0017 makes the boundary **human confirmation**. It does not say that only some kinds of content may be confirmed, and nothing in it distinguishes a preference from a fact.

The restriction that produced this dead end came from somewhere narrower: `remember` is the *keyed* path and refuses non-preference keys, which is correct for what `remember` is. That correctness was mistaken for a rule about what may ever be spoken.

### 2. Two paths, and the deciding fact is that keys are never shown

`_format_memory` renders `value` and `reason`. **A key is identity — for precedence and for dedup — and never reaches a prompt.** That separates two things this project had been treating as one:

| | keyed projection | supplier candidates |
|---|---|---|
| what it is | standing memory | chosen for one message |
| shape | one slot per key | a bounded list |
| holds | **preferences** | **confirmed facts** |
| the key | the relation, meaningful | identity only, invisible |

**The keyed projection stays preferences-only**, and that earlier decision is unchanged rather than overturned. One slot per key genuinely cannot hold facts: a person has many, and flattening them collides on the relation.

**The supplier has none of those constraints**, so a confirmed fact fits it exactly.

### 3. `confirm`, a new act, beside `remember` rather than inside it

`POST /graph/assertions/{id}/confirm` appends a same-triple assertion with `origin="stated"`.

The mechanism is the one [ADR 0008](0008-preferences-are-assertions.md) already established for ratification and is not new: ratification is not a flag that flips, it is **the owner making the claim**, so the proposal stays and the two rows differ in `origin`. `_unrepeated` already keys on `origin`, so the confirming row is not swallowed as a restatement.

A separate act rather than a loosened `remember`, because they answer different questions. `remember(key, value)` states a preference and takes a key; `confirm(assertion_id)` endorses a claim that already exists and takes a row. Merging them would give one function two meanings and a caller no way to say which it wanted.

### 4. A confirmed fact renders through the catalogue's sentence

`Acme —cto→ Diane` becomes *"Diane is the CTO of Acme"* — `Relation.sentence` with node labels substituted, which is the renderer ADR 0009 built for conclusion statements and is reused rather than reinvented.

`reason` is the claim's `attrs.reason`, which is the transcript's own wording. So a candidate arrives as a sentence plus why it is believed, which is what `_format_memory` already assumes and what makes a fact something a model can weigh rather than obey.

The key is the **assertion id**: unique, stable, and never displayed. Nothing has to invent a key, which is the trap that widening the keyed projection would have walked into.

### 5. Only stated facts are candidates, and there is one place that decides

`preferences_for` is the one function reading assertions on behalf of a prompt, and this adds a second — a claims equivalent for the supplier. Both filter `origin="stated"` and nothing else may.

That is two places rather than one, which is worse than [ADR 0010 §5](0010-memory-has-a-port.md) wanted and is the honest cost of two shapes. The mitigation is that they are the *only* two, they sit in one module, and each has a test asserting an `inferred` claim never appears in its output.

## Consequences

**Retrieval becomes buildable and the kill criterion becomes measurable.** With confirmed facts in the graph there is finally something for traversal to choose among, and a comparison against recency measures a difference rather than an empty set.

**The console gains its most important affordance and it is not destructive.** Everything ADR 0009 added takes something away. This is the first act that keeps something, which is also the first one whose absence a person would not notice — the graph works, quietly, without ever mattering.

**Confirmation is now the bottleneck, deliberately.** Nothing auto-confirms. A graph full of accurate extracted facts contributes nothing to a prompt until a person says so, one claim at a time, which is slow and is the property that keeps unreviewed model output out of a system prompt.

**A confirmed fact can still be retracted**, by ADR 0009's route, and the retraction closes the stated row while the inferred one stays. So endorsement is reversible and the log records both the endorsement and its withdrawal.

### The one to dislike

**Two functions now decide what may be spoken, where 0010 §5 argued hard for one.** The guarantee was already weaker than the two-table version it replaced, and this halves it again.

The defence is that the alternative is worse in a way that is easy to miss: one function returning both shapes would need a flag saying which, and a flag is exactly how *speakable* and *not speakable* come to depend on reading a call site correctly. Two named functions, each with one job, are more honest than one function with a parameter.

## Alternatives rejected

**Let the supplier return `inferred` claims and mark them.** Tempting — it makes retrieval measurable immediately, with no confirmation bottleneck. It also puts unreviewed model output into a system prompt, which is the exact escalation ADR 0017 exists to prevent, arriving through a component that looks like plumbing. Marking it does not help: the model reads the text either way.

**Widen the keyed projection to any functional relation.** Already rejected once, and the reasons hold: it flattens a fact about an entity into a string, collides on the relation as a key, and invents key names. What changed since is not this, but the discovery that the supplier is a *different path* with different constraints.

**Auto-confirm facts above some confidence.** There is no confidence on an assertion, only on a conclusion, and inventing one for this would be a number chosen to justify a shortcut. The whole design rests on a person deciding, and a threshold is how that becomes a person deciding once, in advance, about claims they have not seen.

## Not built

**Bulk confirmation.** One claim, one act. The design wants ghosted diffs accepted in bulk, and that is a console affordance over a queue that does not exist.

**Confirming a conclusion.** A conclusion is already a belief with evidence and a confidence, and whether endorsing one makes it speakable is a different question with a different answer — it would be the system's reasoning entering a prompt, not the owner's fact.
