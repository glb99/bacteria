# Dialogue 13 — The subject changed

> Opened 2026-08-28 by the human, after an afternoon spent building an ontology of the `bacteria` codebase and finding that it went onto the substrate without a single change:
>
> *"I think the useful part of the project is for things like architectures designing, business management, research… While the personal assistant was the way of validating the most basic substrate (nodes, relationships creation with things like I have a dog)."*
>
> That reframes what this project is. It is recorded here rather than absorbed quietly, because it changes which questions are load-bearing — and one of the questions it demotes is [§14](../../architecture/memory-graph.md)'s bet, which most of the design so far has been justified by.

## The founding document never said memory

[§1](../../architecture/memory-graph.md) states the thesis as *an explicit, visualizable model of reality, **shared** between human and agent*, and says where the novelty is:

> Every substrate concept below already exists in open source (semantica proves it). What nobody has built is the **negotiation surface**. […] The substrate is known technology; **the interface is the novel work**.

Memory was the first instance of that thesis, not the thesis. Reading back, the word "memory" carries no weight in §1 at all — it arrived from `idea.md`'s framing of the bacteria agent and was never re-examined.

## What building the second instance produced

Not an argument. Three observations from one afternoon, each of which had been reasoned about for weeks without being settled.

**The substrate took it unmodified.** 332 claims about modules and imports went through `observe()` under a reserved scope with no schema change, no catalogue entry, no new node kind. `_KINDS` turned out to be enforced in exactly one place — the extractor's `_clean` — so the "closed six" that [dialogue 11 Q2](11-the-name-and-the-tail.md) called *the binding constraint* binds the LLM path and not the substrate.

**Four policy layers went inert, countably.** `conflicts=0` and `inferred=0` over 332 rows, because no architecture relation is functional. `trust` records who reported and nobody reported. `origin` has words for *stated* and *inferred* and none for *computed*. Valid time duplicates git's. That is [dialogue 10 Q4](10-a-place-to-stand.md)'s substrate/policy table, verified rather than predicted.

**The visual grammar transferred without alteration.** The console's tail styling — dashed and muted, its comment reading *"the claim is not wrong; it is unchecked"* — was written for an unratified relation in a personal graph and is exactly right for 219 imports no boundary speaks to. Nobody ported it; it fit.

And the core interaction reproduced itself verbatim. [§8](../../architecture/memory-graph.md) states it as *"your rule says one employer, this says two; fix the fact or fix the rule?"*. The architecture feature, arrived at independently, produces *"your rule says core imports no feature, this says it does; fix the code or fix the rule?"* — the same sentence with the subject swapped, including the asymmetric authority that makes it a negotiation rather than a lint.

## Three tiers of vocabulary, and we built the wrong one

This corrects a claim made twice in the same conversation, and the correction is the most useful thing in this dialogue.

The first claim was that a codebase's vocabulary is **given** — `module` and `import` come from the language spec, `table` from SQLModel — so [§10](../../architecture/memory-graph.md)'s doctrine (*never author types in advance; propose on the third sighting*) does not apply, because there is nothing to discover.

That is true of tiers one and two and **false of the tier that matters**:

| tier | source | example | discovered? |
|---|---|---|---|
| language | the grammar | `module`, `package`, `import` | no — transcribe |
| framework | the stack | `table`, `route`, `task` | no — transcribe, per stack |
| **practice** | **this codebase's own conventions** | **`feature`, `layer`, `role`** | **yes — the rule of three** |

Tier three is the only one that is *about bacteria* rather than about Python, and it is derivable from regularity: `models`, `repository`, `service`, `views` appear together in four packages and in none of `core`, `entrypoints`, `evaluation`. A **feature** is a package carrying that role set; everything else is a layer or a library.

We shipped tiers one and two. In Palantir's terms that is the **Kitchen Sink** anti-pattern by name — a 1:1 mirror of the source system, here the parser, standing in for a model of the domain. The domain is the architecture; files are the source system.

**And tier three is already in the code, in the wrong form.** `checks.py` holds `CORE = "bacteria.app.core"` and computes *is this a feature* as prefix arithmetic inside each predicate. The concepts are load-bearing in every rule and exist nowhere as types — a vocabulary being used without being named.

Moving them into the graph as claims (`package:chat —is_a→ feature`, never as a node *kind*, which would split one node into two on [dialogue 11 Q2](11-the-name-and-the-tail.md)'s identity argument) does three things: the rules stop containing this repo's package names and become portable, a misfire becomes contestable at the right level — you can disagree with *"chat is a feature"* separately from *"layers do not import features"* — and, most importantly, **classification is the first thing in this domain that is genuinely uncertain.** An import is exact; a classification is a judgment from a regularity. Which is where `origin == "stated"` finally has something to gate, in a domain this dialogue had already concluded made the confirmation machinery inert.

## What is agreed

### One project, and the second subject is what keeps it honest

The sharing is substantial and now evidenced: the bi-temporal log, the confirmation gate, retract and supersede, the four conflict states, the catalogue-with-a-tail pattern, conclusions with evidence and staleness, the action vocabulary, the visual grammar.

The argument is not code reuse, though. **Two domains are what force the seam to be found.** One domain lets policy and substrate stay fused indefinitely; writing 332 rows exposed four inert policy layers in an afternoon after weeks of reasoning had not.

### Personal memory is not scaffolding to be discarded

It earned every hard finding this project has — ten relation names across fifteen rows, the name-claim that minted a second person node, the tail, the store that refused a key — cheaply, because the stakes were one person's dog.

More than that, **it is the closest available proxy for business and research**, and the codebase is not:

| | ground truth | identity resolution | contested |
|---|---|---|---|
| architecture | derivable, exact | a module is its path | no |
| personal memory | none | *which Diane?* | yes |
| business, research | none | *which customer?* | yes, and across people |

Personal memory shares all three columns with the target domains. Architecture dodges all three, which is precisely why it is fast.

### Architecture is the demo, not the proving ground

So *validate on architecture, then scale to business* would repeat the mistake this dialogue is about, one level up. Architecture lights up two of the console's five state dimensions. A surface proven there is proven for derived domains and merely suggestive for the rest.

### Three layers, and only the first differs per domain

- **Generator** — differs entirely. An AST parse, an LLM extractor, human authoring, a connector. Each yields typed claims with an honest origin.
- **Surface, actions, log, negotiation** — shared, built once.
- **Rules** — differ in content, identical in shape: a predicate over types yielding findings.

Which is *one engine, many instances*, with the missing piece named: **the adapter is what a domain is.**

One difference that is not generation and shows up as a feature: **a derived domain regenerates its model under its stated layer.** Delete a module and the boundary governing it is orphaned. A testimonial domain never has this, and nothing in the design handles it.

## Questions

**Q1**: Does [§14](../../architecture/memory-graph.md)'s bet survive the change of subject? *Does traversal beat recency* is a **retrieval** question — it exists because an assistant must choose what to inject into a bounded context. An architecture or business ontology is **queried**, by someone who knows the model's shape, rather than retrieved from by relevance. If the subject has moved, the bet was the central question of the instance being demoted — and a great deal of design, recorded time included, was justified by needing to settle it. Retire it, defer it, or is it still load-bearing?

**Q2**: When does multi-human stop being deferred? [Dialogue 10 Q3](10-a-place-to-stand.md) settled that the two parties are human and agent, and called two *people* "a different product". But architecture, business and research are inherently multi-party, and *shared mental model* has its full meaning only where several people disagree. `constraints.py` forbids cross-scope conflict as a **stated correctness property**. On the new reading that is not a constraint to respect but the main roadmap item — and [the `README` sentence deleted on 2026-08-26](../README.md), *"(and between humans)"*, was the product rather than an overclaim.

**Q3**: Is the architecture prototype scoped to the **surface** rather than to the domain, and what is its kill criterion? The failure mode is building an architecture linter with a good UI. The proposed scope is classification proposed and ratified, the boundary lifecycle in the log, certainty legible in the scene, and staleness when the model regenerates. What would have to be true at the end for it to have proven anything about the negotiation surface, rather than about imports?

---

## Answers & agreed conclusions

### Q1 — The bet survives as a question and dies as a kill criterion, and is replaced rather than retired

**Agreed 2026-08-28.**

**It is a category error in one of the new subjects.** Architecture has no retrieval: you *query* a model whose shape you already know, with no context budget, no relevance ranking and no injection. Traversal-versus-recency is not a hard question there, it is not a question.

**It survives in the others.** A human queries a business ontology, but an agent working inside one still has a bounded window and still must decide what to load before answering. So the question is real — no longer central, and no longer about memory.

**What dies is the consequence clause**, which is the load-bearing half:

> If traversal-based retrieval does not beat recency […] **the graph has not earned its keep**, and the fallback is vectors over confirmed entries.

That was correct while prompt injection was the graph's only consumer. It no longer is. Rule checking, conflict detection, the negotiation surface and plain querying all need the graph and none of them is retrieval, so traversal could lose outright and the graph would still be load-bearing. A vector index cannot say that `core` imports a feature, or that two people disagree about who owns a customer.

**And a retired kill criterion must be replaced, or the project stops being able to be wrong.** *The product changed, so my falsifiable claim no longer applies* is the standard unfalsifiable move, and [§14](../../architecture/memory-graph.md)'s whole virtue was being stated so it could be lost. The replacement lands on what [§1](../../architecture/memory-graph.md) actually claims is novel:

> **If the human accepts essentially everything the agent proposes, there is no negotiation.** The surface is a rubber stamp, the "shared" model is the agent's model with a signature on it, and the thesis is wrong.

Measured as the proportion of proposed classifications and boundaries that are **rejected or edited** rather than waved through. Near zero is the failure, and [§8](../../architecture/memory-graph.md) already names it — *"a review everyone clicks through is worse than no review, because everyone believes it was checked."* It needs no personal data and no months of accumulation, so unlike the bet it can be settled on the architecture prototype in weeks.

**Recorded time survives on changed grounds, and this needs saying explicitly.** §14 justified it by needing to replay past runs to settle the bet. Drop the bet and that justification goes, but the conclusion holds: *which boundaries were stated when this crossing was accepted* is a recorded-time question, and decision lineage needs it in every domain. Left unsaid, someone later reads recorded time as orphaned machinery and removes it.

### Q2 — It stops being deferred at the architecture prototype, and only one of its four parts is due

**Agreed 2026-08-28.** The premise of the deferral has already expired quietly, which is why this is not a scheduling question.

[Dialogue 10 Q3](10-a-place-to-stand.md) deferred multi-human because v1 has one owner. [Dialogue 10 Q2](10-a-place-to-stand.md) then put the architecture ontology under a **reserved scope in `user_id`** — a scope with no owner at all. `constraints.py`'s guarantee, *"one person's graph can never produce a conflict against another's — a correctness property before it is a privacy one"*, is **vacuously true** there, which is a different thing from being satisfied. The next thing to be built is already outside the assumption, and a codebase ontology is for a team by its nature.

**But multi-human is four things and they are not due together.**

| | defer | why |
|---|---|---|
| access control | yes | well understood, orthogonal, mechanical to add |
| consensus — one claim wins or both stand | yes | cannot be designed before real disagreement is seen |
| cross-scope conflict | yes | widening a comparison is a code change, not a migration |
| **who stated it** | **no** | absent everywhere, and unreconstructable afterwards |

`trust` records *how a claim arrived* — user, third-party, inferred — and nothing records **who believes it**. In a single-owner graph the author is implicit; in a shared scope it is simply missing, and a row written unattributed is unattributable forever. Adding one later is exactly the manufactured history [§2](../../architecture/memory-graph.md) forbids.

**The counterweight, recorded because it weakens the case.** There is one human today, so every existing row *is* attributable by context and deferring costs almost nothing right now. The reason to do it anyway is not the migration — it is that each feature built on *one owner per scope* is another thing to unwind, and the prototype is about to be one of them.

**The smaller prior question, which is harder to dodge**: `user_id` does two jobs, owner and partition, and they coincided until this afternoon. Either split them into `(ontology, scope)` or write down that the column is overloaded and what that costs — [dialogue 12 Q1](12-nothing-ever-leaves.md)'s move, a paragraph now against an argument later.

**The `README` sentence stays out.** The direction belongs here, where directions live; *"(and between humans)"* goes back into the founding document when it is true. Restoring it now recreates the overclaim removed on 2026-08-26, and the reason for removing it was sound — a founding document writing cheques the design refuses to honour is how a project is surprised by its own scope.

### Q3 — Scoped to the surface, and the scope falls out of the kill criterion

**Agreed 2026-08-28.** The scope is not chosen by taste. It is whatever [Q1](#q1--the-bet-survives-as-a-question-and-dies-as-a-kill-criterion-and-is-replaced-rather-than-retired)'s replacement criterion needs in order to be measurable at all.

**Both tails are failures**, which the first framing got wrong. Near-zero rejection is a rubber stamp; near-total rejection means the agent has no model worth arguing with. Negotiation lives between them, and a one-sided threshold could be satisfied by proposing deliberate junk.

**So the criterion dictates the contents.** A rejection rate is undefined unless something *uncertain* is proposed, which settles what must be in:

- **Tier-three classification** — `chat is a feature`, `core is a layer`, `service.py has role service` — proposed from regularity, `origin: inferred`, ratifiable. **Non-negotiable**: it is the only uncertain thing in this domain, so without it there is nothing to reject and the prototype cannot evaluate itself. It is also the only part that makes this an ontology of *bacteria* rather than of Python.
- **The boundary lifecycle in the log** — stated, crossed, accepted with a reason, retired with a date. The loop, not merely the check.
- **Certainty legible in the scene.** A computed violation and a proposed classification must not look alike, or the second is trusted like the first — [analysis 11](../analysis/11-hq-spatial-monitor.md)'s warning arriving as a design constraint.
- **Regeneration and staleness.** Delete a module and the boundaries governing it are orphaned. Unique to derived domains, and unhandled anywhere in the design today.
- **`stated_by` on every stated row**, per [Q2](#q2--it-stops-being-deferred-at-the-architecture-prototype-and-only-one-of-its-four-parts-is-due).

**Explicitly out, said in advance so a success is not over-read**: identity resolution (a module is its path), trust tiers (nobody reported anything), retrieval (nothing is injected into a prompt), cross-scope conflict. Architecture lights up **two of the console's five state dimensions**.

**The trap has a name and it belongs on the wall: *an architecture linter with a good UI*.** Everything on that list except classification is linter work. Classification is the only part that is the product.

**Time-boxed at three weeks**, honouring [dialogue 10 Q2](10-a-place-to-stand.md)'s condition, with a stop rule sharper than a date: if nothing was ever proposed, or nothing was ever rejected, it failed **regardless of how good it looks**, because in both cases the number it exists to produce is undefined.

---

## Closing note

All three answers turned on the same discovery, and it is worth naming because it is likely to recur: **a decision's justification had expired while the decision still looked sound.**

The bet's consequence clause was correct when the graph had one consumer and false once it had four. The multi-human deferral's premise — *v1 has one owner* — was true until [dialogue 10 Q2](10-a-place-to-stand.md) agreed to a reserved scope that has none, in the same dialogue. The prototype's scope looked like a matter of taste until the kill criterion made it derivable.

None of the three was wrong when written. Each stopped being right without anything announcing it, and all three were found by building the second instance rather than by re-reading the first. That is [dialogue 05](05-what-building-it-taught.md)'s closing line holding for the sixth time — the repository has been a more reliable witness than the record of it — with one addition this dialogue supplies: **the record's most dangerous entries are not the wrong ones but the ones whose reasons quietly lapsed.**
