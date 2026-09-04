# Dialogue 10 — A place to stand in

> Opened 2026-08-26 by the human, after reading [source 11](../sources/11-hq-spatial-monitor/source.md) — an infrastructure monitor rendered as a colony on Mars. The proposal is not the colony. It is that **the way the model is shown deserves real investment**, and that the shown model should be one you can *act from*: modules and their connections for a codebase, with tests runnable from the view; departments and their relations for a business, with inferred warnings and actions to take.
>
> [Analysis 11](../analysis/11-hq-spatial-monitor.md) argued against the colony on the grounds that it is read-only, edgeless and closed-vocabulary. **This proposal answers the first of those**, which is the one that mattered, and it moves the question from *should we make it pretty* to *what is the surface for*.

## Why the objection from analysis 11 does not carry over

The colony is a monitor. You look at it and it tells you; there is no move you can make from inside it except to collect a charge. That is what made a prettier read surface look like a way to *postpone* [dialogue 09](09-the-write-routes.md)'s gap rather than close it.

A surface you can act from is not that. It is [§8](../../architecture/memory-graph.md)'s negotiation surface with a different geometry — and §8 already calls that layer the differentiating one, and already notes that no source builds it.

**And the sequencing objection was wrong**, which is worth stating plainly because it was stated the other way a few hours earlier. [§14](../../architecture/memory-graph.md) is explicit:

> Minimum graph → negotiation surface → traversal and vectors. […] **The surface is also not speculative spend** — it is the review queue, which is needed whether or not edges ever earn their keep.

Investing here is the plan, not a detour from it. The hedge in analysis 11 — *revisit once the bet is settled* — reads §14 backwards: the surface comes **before** traversal precisely so the bet is not settled on an uncurated graph.

## The argument that does not come from the source

The best case for spending real effort on the visual form is not HQ's. It is in what this model already decided to represent.

| dimension | states |
|---|---|
| valid bounds | known / open / unknown, **at each end** |
| overlap | true / false / undecidable |
| conflict | none / conflict / possible / explained |
| trust | user / third-party / inferred |
| vocabulary | canonical / tail |

A console row makes a person read five columns and combine them in their head. **`possible` and `explained` are the distinction the entire inference layer exists to produce, and as adjacent text cells they read as synonyms.** The three-valued logic of §5 and the four states of §6 were chosen over collapsing precisely because the difference is load-bearing — and then rendered in the one medium that flattens it again.

HQ's Sol 007 rule — *colour before text, a state has to land before you read a word of it* — applies harder to this data than to its own. Infrastructure is binary; this is not.

## The two examples are opposites

The proposal offered a codebase and a business as interchangeable illustrations. They are not, and the difference decides what each is good for.

**Code has ground truth.** The import graph is *derivable* — parsed, exactly, completely, at no cost and with no model involved. A module is its path, so identity resolution does not arise. There are no trust tiers, because nothing was reported by anyone. Bi-temporality is git's already. There are no contradictions: a file imports or it does not.

**A business has none of that.** Who reports to whom, what a team owns, when a role ended — the contested, ambiguous, bi-temporal material the assertion log exists for.

So the code version would work beautifully and **exercise almost nothing this project is uncertain about**. It is a graph visualizer over a parsed tree. The business version exercises everything and has no ground truth to check itself against.

**Which makes them a sequence rather than a choice.** The code one is the rehearsal: the only version where you can tell whether the rendering is *correct*, because the truth is computable. Learn the visual grammar where mistakes are detectable, then apply it where they are not.

It also has a deliverable sitting in `bacteria` already: `diagram.excalidraw`, hand-maintained and drifting. A hand-drawn architecture diagram that disagrees with the code is exactly the cognitive debt the proposal is aimed at, and deriving it is worth doing whatever happens to the rest.

## The line this must not cross by accident

"Run tests from the view" is a **world-action**. "Retract this claim" is a **model-action**. [§7](../../architecture/memory-graph.md) separated them deliberately:

> Only model-actions flow through it in v1; world-actions route through the same place later.

Palantir merges them — actions are first-class ontology citizens, and that is the eventual shape. But the write routes are days old and have not been used on the real graph once. A surface that runs tests is v2 of a v1 nobody has exercised, and the validator seam §7 puts between *proposed* and *committed* has only ever had model-actions through it.

The risk is not that world-actions are wrong. It is that a view which does both makes the distinction invisible at the exact moment it starts to matter.

## Questions

### Q1 — One surface or two?

The recommendation in conversation was **not a third surface**: give the console's existing graph tab this treatment, since it already holds the data, the layout modes and now the write routes. Conflict state as colour before text; tail visibly unlike canonical; correction reachable from the mark rather than from a row.

The alternative is that a genuinely spatial view is a different artifact from a console and trying to grow one into the other produces neither.

**Question**: evolve the console's graph tab, or accept that this is a separate surface with its own budget?

### Q2 — Is the architecture ontology part of this project, or its own?

It is the rehearsal above and it is also a different thing: derived rather than extracted, complete rather than partial, verifiable rather than contested. It would use none of the assertion log, no trust tier, no conflict state — arguably not this ontology at all, only the same rendering.

**Question**: build it as an instrument for learning the grammar and say so, or keep it out on the grounds that it shares only the visuals?

### Q3 — What does the shared mental model actually need?

[Analysis 11](../analysis/11-hq-spatial-monitor.md) noted HQ is single-player: it is *your* estate, with no affordance for two parties disagreeing about what a building means. The stated motivation for all of this is **sharing** a mental model — between a person and their agent, and between people.

Nothing in either proposal so far addresses two viewers who disagree. Seeing the same thing is not the same as agreeing about it, and §8's surface is named *negotiation* for a reason.

**Question**: is the goal one person seeing their model clearly, or two parties reconciling theirs? They are different designs, and the second is the one the project's own thesis asks for.

---

## Answers & agreed conclusions

### Q1 — Neither, because the question contained two

**Agreed 2026-08-26.** Reading the console settles it differently from how it was asked. `frontend/src/graph.ts` is six hundred lines that **draw nothing** — no SVG, no canvas, just `<section>`/`<ul>`/`<li>` grouped into columns by subject or relation. And it already carries the actions: `confirmable`, `linkButton`, `action`, conflict rendering, trust summary. [Dialogue 09](09-the-write-routes.md)'s write routes are wired into it.

**So the console is not missing the negotiation layer. It is missing the visual grammar.** Which separates two decisions that had been travelling as one:

**(a) Visual grammar on what already exists.** Conflict state as colour before text, tail visibly unlike canonical, the five dimensions legible at a glance. This is CSS and class names over DOM that is already built — no new surface, no dependency, no architectural commitment. It is not a surface question at all.

**(b) A node-link diagram.** Needs a layout algorithm: hand-rolled SVG plus force or hierarchy, or a dependency. The console has exactly **one** runtime dependency, `openapi-fetch`, and adding a graph-drawing library runs hard against that grain. This is where "a different artifact" becomes true.

**Agreed: (a) now and unconditionally; (b) judged afterwards on evidence from (a).** Three reasons.

**(a) is the cheapest available experiment on whether (b) is needed.** If colour-before-text makes `possible` and `explained` land on a list, the diagram is solving a problem that no longer exists. If it does not, what the list failed to show is the *specification* for (b) rather than a guess at it.

**Diagrams win at scale and at paths, and neither applies yet.** The graph is personal-scale, and the thing most needing to be seen — two claims contradicting each other about one subject — is a *pair*, which a grouped list shows well and a force layout may scatter.

**(b) is where the third-surface risk lives** — a beautiful world over contested data, which [analysis 11](../analysis/11-hq-spatial-monitor.md) warned makes a wrong graph look authoritative. Deferring costs nothing, because (a) is a prerequisite either way: a diagram needs the same colour vocabulary the list does.

**What would reopen it**: if Q3 answers that the goal is two parties reconciling rather than one person reviewing, a list may be structurally wrong — you cannot point at a table row the way two people can point at a place. Q3 should decide (b), not the reverse.

### Q2 — Build it, on the substrate, under a reserved scope

**Agreed 2026-08-26**, and it revises the recommendation this dialogue started with. The first answer was *keep it out of `graph_assertion`*, which [Q4](#q4--generalizing-to-other-ontologies-the-substrate-travels-the-policy-does-not) makes blunt: an architecture ontology built outside the graph package would teach nothing about the seam Q4 just agreed to mark. It would be a separate program that happens to draw boxes.

**Built on the substrate, the seam stops being aspirational.** The first thing that chafes says where the line is.

**The mechanism is a reserved scope value in `user_id`** — the same trick as the derived owner node id — rather than a new column. Four reasons it is the right size:

- **No schema change.** Renaming `user_id` to a general scope key across the package, to serve a development tool, is the premature hardening [§14](../../architecture/memory-graph.md) warns about.
- **Complete partition**, since every query is already keyed by `user_id`. That was the real content of the original "do not pollute the log" objection, and it is satisfied without a second store.
- **It is a live experiment on Q4.** The rows will carry a `trust` value that means nothing, no `self` node, and constraints that are domain law rather than personal hypotheses. The policy layer will be *felt* not fitting, specifically, instead of reasoned about.
- **Reversible** by deleting one scope.

**Three jobs, in the order they actually matter:**

1. **The only dataset that can answer Q1(b)** — real scale and genuine path questions, which a personal graph will not have for a long time.
2. **The first concrete probe of Q4's seam** — which abstractions survive a domain with no "I", no adversary and no contested claims.
3. **A deliverable regardless** — `diagram.excalidraw` is hand-maintained and drifting out of agreement with the code.

**Held to one test**: if it gets built and the question *does a diagram beat a list* is still open, it was decoration. Time-boxed, because this is the tractable problem sitting next to the hard one, which is the classic shape of displacement.

**In `bacteria`, not here.** This repository's deliverable is the mental model; a code visualizer is not that.

### Q3 — Human and agent, and the founding document overclaims

**Agreed 2026-08-26.** The question turns out to sit on a tension present since the first line of this repository.

[`README.md`](../README.md) says the ontology is *"a shared mental model between a human and their AI agent **(and between humans)**"*. `constraints.py` says the second half cannot happen:

> one person's graph can never produce a conflict against another's. That is a **correctness property** before it is a privacy one, but it is both.

The project claims multi-human and the implementation forbids it — not as a gap, as a guarantee.

**The two readings cost wildly different amounts.**

**A — the two parties are the human and the agent.** Largely *already designed*, and the design is better than it looks. The agent has a distinguishable voice in the data: `trust: inferred`, and conclusions in their own table with `derived_by ∈ {llm-judgment, constraint-inference}`, defeasible and rejectable. That is exactly "the agent holds a view the human may overrule."

What is missing is the **interface, not the model**. The console renders trust as a *column*, and nobody negotiates with a column. Negotiation needs voices legible as voices — *you told me this* / *I read this somewhere* / *I worked this out*. **A claim cannot be contested if it is not visible who is making it**, and that is the difference between a log one inspects and a model one argues with.

**B — the two parties are two people.** Business, science, a team. It needs cross-scope conflict, which is the deliberately forbidden thing; provenance per *party* rather than per channel, since `trust` records how a claim arrived and never who believes it; a consensus model deciding whether one claim wins or both stand; and access control, which does not exist at all. [Q4](#q4--generalizing-to-other-ontologies-the-substrate-travels-the-policy-does-not) already showed the policy layer would need rewriting to get there. It is a different product.

**Agreed: build A, declare B out of scope for v1, and stop claiming it.** Three reasons.

**A is unbuilt, cheap, and is the current phase** — Q1(a) is already agreed, and *render the voices* is the content that change should carry rather than a second effort.

**A is a prerequisite for B in any case.** If two voices cannot be rendered legibly, five researchers certainly cannot. Doing A first is step one of B rather than a compromise against it.

**The README is writing a cheque the design refuses to honour.** An unearned claim left in a founding document is how a project is surprised by its own scope later. Corrected in the same commit as this answer, with the deferral and its reason stated rather than the phrase silently dropped.

**This settles Q1(b): the diagram stays deferred.** The stated reason for possibly reopening it was that two parties cannot point at a table row the way they can point at a place — and that argument only ever applied to B. Under A the second party is a system with no eyes, so a shared place buys nothing.

### Q4 — Generalizing to other ontologies: the substrate travels, the policy does not

**Raised by the human 2026-08-26**: that the graph should be a way of viewing *any* category of ontology or mental model — a business, an architecture, a field of science — rather than a personal memory specifically.

**The instinct is already half in the model.** [§11](../../architecture/memory-graph.md) asks for "a stable generic core (query, assert, traverse, subscribe) that survives schema change" and for lossless export to RDF/JSON-LD with SHACL shapes. [§1](../../architecture/memory-graph.md)'s thesis — an explicit, visualizable model of reality, shared and negotiated — never mentions memory. Palantir is the existence proof that one engine serves many domains.

**But two layers are bundled and only one of them travels.**

| substrate — domain-neutral | policy — justified by personal memory specifically |
|---|---|
| bi-temporal assertion log | **trust tiers** — exist because a transcript carries attacker-controllable text |
| three-state bounds | **reserved floor / two surfaces** — a prompt-injection defence |
| three-valued overlap | **auto-commit without review** — safe *only* because assertions never reach a prompt |
| four conflict states | **the `self` node** — meaningless where there is no "I" |
| derived canonicality | **constraints as contestable personal hypotheses** — "a person has one employer" is a rule *a particular person* may reject |
| identity linked, never merged | **recorded time** — justified by ADR 0020 replaying a past agent run |

Nearly every hard-won decision in this project sits in the right column, and each is justified by a threat model or a workflow another domain does not have. In biology, trust is not a channel marker that deliberately never upgrades — it is evidence quality, ordinal and combinable. Constraints are not personal opinion but domain law, which inverts the whole "rules keyed by owner" plan. **Generalizing is not a feature; it is finding that seam and naming it.**

**Two of the three examples break something structural.** Business and science are inherently multi-party, and the design is single-owner *as a stated correctness property* — `constraints.py`:

> Pairs are compared within a `(user_id, src)` group, so one person's graph can never produce a conflict against another's. That is a correctness property before it is a privacy one, but it is both.

A research group's value is that two researchers' claims **do** collide; a business ontology is contradictory across departments by nature. Those domains need exactly what is currently forbidden by construction.

**So this forces [Q3](#q3--what-does-the-shared-mental-model-actually-need).** §1 says "shared between human and agent" — two parties, but only one of them a person with a conflicting view of their own. Business and science need multi-*human*, which is a different design and not a configuration flag.

**Agreed direction: do not build multi-domain; mark the seam.** Be disciplined from now about which column each decision belongs to, in the ADRs and the module layout. It costs almost nothing today and is the whole difference between *generalizable later* and *a rewrite*. The precedent is in the same repository: `backend/agent/` is vendorable, numbers its own ADR sequence, and its README explains why — "a record about FastAPI Cloud would be noise there."

**The caution.** [§14](../../architecture/memory-graph.md)'s bet is unsettled, so generalizing now risks generalizing something that has not earned its keep — and multi-domain is a reliable way to make v1 never ship, since every decision hardens once it must serve hypothetical domains.

**Effect on [Q2](#q2--is-the-architecture-ontology-part-of-this-project-or-its-own), which is still open**: it strengthens the case for the architecture ontology. It is the safe first probe of exactly this question — a second instance of the same machinery, one domain, no multi-party problem — and it reports which abstractions survive contact with a different world. That is a better reason to build it than either of the two already recorded.
