# The memory graph

The conceptual model behind `backend/app/src/bacteria/app/graph/`. What the
model *is*; the [dialogues](../research/dialogues/) say *why*, and the
[ADRs](../adr/README.md) say what was actually decided and built. Where this
file and an ADR disagree, the ADR wins — it is the record; this is the
synthesis it was drawn from.

> **Status: v1 agreed 2026-08-22; reconciled with the codebase 2026-08-23;
> first corrections from implementation open in
> [`dialogues/05`](../research/dialogues/05-what-building-it-taught.md) as of
> 2026-08-24.** Synthesised from sources 01–09 and settled question by question
> in [`dialogues/01`](../research/dialogues/01-initial-questions.md), then
> reconciled against the codebase in
> [`dialogues/03`](../research/dialogues/03-bacteria-reconciliation.md). Those
> hold the reasoning and citations behind every decision here. Vocabulary in
> [the glossary](../research/glossary.md).

---

## 1. Core thesis

The best way to solve a problem is to understand it as deeply as possible, which means modeling the reality around it — its entities, relationships, and abstractions. An AI agent's memory should therefore not be a flat store of facts but an **ontology**: an explicit, visualizable model of reality **shared** between human and agent.

Two traditions define "shared model" identically, which is good evidence the thesis is sound. Gruber (1993): an ontology is "a formal specification of a **shared conceptualization**." DDD: the ubiquitous language emerges from "a feedback loop that creates a **united mental model** within the team." Bacteria's memory graph is the ubiquitous language of the human–agent team, and the graph UI is where that language gets negotiated.

**The differentiation follows from this.** Every substrate concept below already exists in open source (semantica proves it). What nobody has built is the **negotiation surface** — a graph where human and agent jointly propose, contest, and ratify a model of reality. The substrate is known technology; the interface is the novel work.

## 2. Cross-cutting principles

1. **Model reality, not systems.** Object types represent things in the user's world, never the shape of a chat log, an email schema, or a storage format.
2. **Deterministic substrate, probabilistic reasoning above it.** Graph construction, validation, provenance and derivation require no LLM.
3. **The feedback loop is the product.** The ontology is never built silently and presented as finished.
4. **Never require the user to think like an ontologist.** They bring domain truth; modeling vocabulary is the agent's problem.
5. **When a decision is asymmetric, take the reversible side.** Adding a capability later is usually safe; removing one the model has grown into is not.
6. **An assumed value never enters the log.** It lives in the conclusion that assumed it, and readers consult that conclusion. Writing an assumption in as though observed makes it invisible exactly when it starts mattering, and lets the next inference read it as fact.
7. **Everything the agent does becomes part of the model.** Observations, conclusions, decisions, actions. Memory is not a cache beside the loop; it is the loop's ledger.
8. **Append-only governs revision, not lifetime.** Nothing is edited: a correction is a new assertion and the old one's belief closes. That forbids **backfilling** — inserting a belief the system never held, which manufactures a false history — and it was never a promise that a row is immortal. **Deletion is a different act**: it removes a belief that was genuinely held, breaking *replay fidelity* rather than honesty, and a decades-scale store of somebody's personal life will be asked for it. So erasure is exceptional, knowingly costs the ability to reconstruct a past run, and must leave a mark that something was removed — an erasure indistinguishable from a row that never existed is the false history this principle actually forbids. Reading the rule as *nothing ever leaves* is how that became the design without anyone choosing it ([dialogue 12](../research/dialogues/12-nothing-ever-leaves.md)).

## 3. The substrate

**Append-only.** Facts never overwrite. This is forced, not preferred: conclusions go stale when their evidence changes (§6), which is undetectable if the change destroyed the prior value; and contradictions are retained rather than resolved (§8), which requires properties to hold several values at once.

**The action log is the event log.** Every model change is an action carrying actor, timestamp and reason (§7). Append-only means those are never deleted and the graph is *derived by folding them*. A committed action is precisely a past-tense record of what happened, so no separate "domain event" concept is needed. Current state is a materialized projection; the log is the truth.

**Three layers, and only the middle one is precious.** The **transcript** is the raw source. The **assertion log** is claims with provenance, both time axes, actor and ratification status. The **projection** is the current-state graph, embeddings, derived properties and staleness marks, folded from the log. One rule decides membership: *can it be regenerated deterministically from what is kept?* If a non-deterministic model call or a human decision went into it, it is durable. The projection is disposable precisely because its inputs are not.

**Bi-temporal, and both axes are mandatory.** Every assertion carries **valid time** (when true in the world) and **recorded time** (when believed). These diverge constantly in personal memory — *today I learned Alice left her job in March* — and both axes are what let the system distinguish a bad inference from a late discovery, protecting past conclusions from unfair invalidation. Valid time alone cannot answer *what did we believe last Tuesday*: filtering today's beliefs to a past interval returns what we think **now** about Tuesday. The asymmetry is decisive — valid time can sometimes be recovered later from testimony, **recorded time can never be backfilled**. Interval-algebra querying stays deferred.

**A temporal bound has three states, and the third is not optional.** An end is *known*, *open* (has not ended; true now and continuing), or *unknown* (may or may not have ended). Collapsing open into unknown was the model's most expensive unexamined shortcut: written as `[?..]` in prose, a reader supplies the intent automatically and code cannot. Stored as an infinity sentinel for open and a null for unknown, which keeps null meaning what it means everywhere else. Starts need only two states. The consequence that earns it: open means *true as of now*, so **two open-ended intervals definitely overlap** whatever their starts, which is what lets a contradiction between two current claims fire honestly rather than by pretending either claim reached back forever.

**Assertions are addressable.** Each carries a stable identity of its own, not the identity of the triple it states — a relation may be believed, retracted and believed again, and each is a separate assertion. Evidence links (§6) pin to that identity, which is what keeps a past conclusion's premises from being silently rewritten by a later revision. Closing an assertion's recorded interval is bookkeeping metadata, not an overwrite of the fact.

**Provenance on every assertion**, using PROV-O's vocabulary (entity / activity / agent, `wasGeneratedBy`, `wasDerivedFrom`, `wasAttributedTo`). Assertions are entities, actions are activities, human-and-agent are agents.

**Identity is separate from observation.** An observation says *an entity called "Diane Mercer" appeared in this email*; identity resolution says *that observation and this one refer to the same person*. Consequently **entities are never merged — identities are linked**. A merge asserts `sameAs`; the underlying observation sets survive; the merged entity is a projection; unmerge is a retraction; **split is a first-class inverse**.

Storage is a pragmatic **property graph**. Triples were rejected because per-assertion provenance, n-ary events and bi-temporality are all awkward in RDF and natural in LPG.

## 4. The meta-model

Borrowed from Palantir's vocabulary, reduced to what earns its place.

| Construct | Use |
|---|---|
| **Object type / object** | A thing or event in the user's world |
| **Property** | A characteristic; may be multi-valued over time |
| **Struct property** | Grouped fields that aren't a thing (an address), carrying their own metadata |
| **Link type / link** | A binary relationship; may carry light scalar properties |
| **Interface** | A capability or contract (`Schedulable`, `Contactable`); multi-level, multi-inheritance |
| **Derived property** | Computed from the graph rather than stored |
| **Action type** | A named, validated change to the model (§7) |

**No subtyping between object types.** Taxonomy is expressed through interfaces (`Dog implements Animal`), which answer aggregation queries without coupling and compose freely. Types sharing fields without sharing kind use **shared properties**. This forecloses the failure mode created by §10: an LLM allowed to subtype will build `Person → Colleague → CloseColleague` one reasonable proposal at a time.

**Two promotion rules, one test.** *Would you point at it and call it a thing?* If yes it is an object; if it is a bundle of fields about something else it is a struct; if it is what-you-can-do-with-this it is an interface. So: when a relationship starts wanting more than a scalar or two, or gains a third participant, **promote it to an event object**. Reified/object-backed link types are not built — n-ary and property-rich relationships are events, and source 03 confirms an object type may model an entity *or an event*.

## 5. Logic

Three **declarative** tiers, attached to *types* (instance-level exceptions permitted) and stored as **data, not code** — arbitrary code would need a runtime and a sandbox, and would destroy the property that a human can read and contest a rule.

- **Constraints** reject illegal states. A six-construct kernel captures ~90% of the value: *functional* (at most one value), *enumerated range*, *domain/range* on links, *disjoint*, plus *inverse* and *transitive* as cheap derivations. Each must be **explainable in one sentence**, because §8 lets the user contest them. **Constraint evaluation is three-valued** — satisfied, violated, or *undecidable because a bound is unknown* — which is not a policy choice but simply what a comparison returns once unknown is a real state. A violation that cannot be decided is a **possible conflict**, shown as such.
- **Derivations** compute rather than store: days since last contact, open threads per project, stale-contact flags. This is what makes the graph feel intelligent with no LLM involved.
- **Preferences and definitions** — the user's own rules about their own world ("nothing before 10am", "*the project* means the most recently touched one"). This is the true personal analogue of enterprise business logic. Today it hides as prose in system prompts; as first-class objects it becomes inspectable, editable, versioned, and visible beside the facts.

**The line between logic and conclusion is *entailed versus assumed*, not human versus machine.** LLM judgments are conclusions, but so is a fully deterministic rule whose output further evidence could defeat. Days since last contact is *implied* by what is stored; *"she became CTO when he left"* is not — the same data is equally consistent with a gap. Derivations are entailed and recomputed silently; **defeasible inferences are conclusions**, carry evidence, and say which rule produced them. Constraints are the commonest source of them: a functional constraint plus one known boundary is real evidence about an unknown one.

**Retrieval: traversal answers *what is connected to this*, similarity answers *what is about this*, and the memory needs both.** They are not alternatives — a graph query must start somewhere, and nothing in a raw message names the starting node. Similarity is the step that makes traversal possible:

> message → **anchor resolution** (exact identifier → lexical/alias → vector similarity) → **bounded traversal**, mostly one hop → rank → candidates.

Two distinct jobs use vectors, and conflating them wastes both: **entity linking** embeds short strings (names, aliases) to resolve text to a node — which is also the missing implementation of §8's entity-resolution confidence bands — while **semantic retrieval** embeds assertion and conclusion prose. A node label like "Diane Mercer" embeds to almost nothing; meaning lives in the claims about it. Embeddings are projection, disposable because their input is durable.

The honest counter-position deserves to sit here rather than be discovered later: a vector index over confirmed facts, with no edges at all, is plausibly sufficient and far cheaper. It is declined because relations between facts are the thing being asked for and a vector index cannot represent one — but that is §1's bet, and §14 says how it would be falsified.

## 6. Conclusions and decisions

Two distinct object families, deliberately split.

A **Conclusion** is a *belief* — "Alice is probably the decision-maker at Acme." It links to its subject entities, to the **assertions that support it**, and to the rule or LLM invocation that produced it; it carries confidence and a lifecycle: derived → active → stale → superseded or retracted. It keeps prose reasoning *in addition to* those links, because a human needs to read why in natural language.

A **Decision** is a *choice* — "therefore email Alice, not Bob." It links to the conclusions it rested on and the actions it triggered. Once executed it is history: immutable, evaluable only in hindsight through a separate linked evaluation.

**Evidence links are mandatory**, because they enable the one operation that justifies this layer: when a fact is revised or retracted, walk to every conclusion that depended on it and mark it stale. Without that, this is an audit log; with it, the memory self-corrects. They pin to assertion *identities* (§3), never to triples.

**A conclusion is never collapsed into the approval queue.** It is tempting — a queue already exists and a conclusion is something to review — but three things do not fit. A proposal's lifecycle is terminal (proposed → activated | rejected) and has no `stale`, which is the state that justifies the layer. A queue keyed one-row-per-key overwrites idempotently on re-run, while two conclusions about one subject are both legitimate and a superseded one must survive. And proposals are conversation-scoped, while a conclusion is about entities and remains a belief in the next conversation.

**Activation emits; the retrieval path learns nothing new.** When a human accepts a conclusion, that action writes an ordinary memory entry carrying its prose and a back-link. This keeps the boundary at the memory API intact and means the agent never has to learn what a conclusion is.

**Staleness demotes; it never deletes.** A stale conclusion stops being supplied as a candidate while the entry and the human's acceptance survive, and it returns for review saying which evidence went. Continuing to tell the model something known to rest on retracted evidence is worse than briefly not telling it something true — and removing something from a projection needs no human, whereas deleting a human's decision does.

Kept from semantica: confidence scores, decision-to-decision causal links, and **precedent search** — *what did I conclude last time in a situation like this*.

## 7. Actions and the agentic loop

**Actions on the model** are first-class in v1: create entity, merge identities, assert or revise a relation, record or retract a conclusion, rename a type. They are internal and reversible, and they are needed regardless, because every change requires an actor, a timestamp and a reason. Keep the set **small and general** — Action Sprawl is the anti-pattern to fear.

**Actions on the world** (send email, write file, call API) are deferred. Each tool registers a thin action-type stub — name, object types touched, read-only versus mutating — with no validation engine behind it. Lineage is captured from day one; preconditions switch on later without restructuring.

**Action types are simultaneously the model's verbs, the validator's units, and the agent's toolset.** Palantir states actions "can be automatically surfaced as tools for all types of agents," and that closes the loop neatly.

**The validator seam sits exactly where Coyle puts it**: after an action is proposed, before anything commits. *Pydantic at the door, ontology at the ledger.* Only model-actions flow through it in v1; world-actions route through the same place later.

## 8. The negotiation surface

The differentiating layer, and the one no source builds.

**Three responses to a write, not two.** *Reject* malformed input — type violations, out-of-enum values, functional-property breaches. *Flag* factual contradictions rather than rejecting them: both assertions land with their provenance and the conflict becomes visible, because a system that models reality must be able to represent that reality *is* contradictory. *Accept* everything else.

**And a flagged conflict may itself be undecided** — two claims that would contradict each other if their dates overlapped, where the dates are not known. This is the same move as `possibly-same-as` below, applied to time instead of identity: represent the uncertainty rather than force a verdict, render it as a *possible* conflict, and let it resolve when one date arrives.

**A conflict is *explained*, never quietly cleared.** Four states, then: none, conflict, possible, and explained — undecided but with an active conclusion accounting for it, typically a constraint-driven boundary inference (§5). The badge does not disappear; it turns from a question into an answer carrying a citation and a confidence, which the user can contest. Left to accumulate, permanent possible-conflicts would become a marker that is always on and therefore never read — the notification-fatigue failure in another costume — so explaining them is not decoration.

**Asymmetric authority.** The agent's writes are validated and refusable. **The user's writes are never blocked** — a constraint violation opens a negotiation: *your rule says one employer, this says two; fix the fact or fix the rule?* Unlike Foundry, where constraints encode organizational authority, here the constraint layer is a **contestable hypothesis about the user's world**, and the user is the domain expert who may overrule it.

**Staging, in two forms on one mechanism.** A branch is just *a set of actions not yet applied*. **Approval staging** (v1) is actions marked proposed and meant to be committed. **Hypothetical staging** (v2) is a named set of proposed actions the graph is viewed *through* and then discarded — *what if I took that job? what if Alice isn't the decision-maker?* — letting derivations and the conclusions engine recompute against a counterfactual. That second form is idea.md's "reality modeling engine that guides decisions" at its most literal.

**Two surfaces, governed differently.** Writing to the graph and contributing text to a prompt are not the same act, and collapsing them forces a false choice between notification fatigue and memory poisoning. **Graph writes are risk-weighted**: what exists, what is traversable, what renders, what a contradiction can fire against. **Prompt text is confirmed only, always**: nothing a model produced reaches a later turn unless a human accepted it, because memory injected into a system prompt is an instruction that outlives the message carrying it.

That split has a hole, and closing it is a condition of using it. A bounded context window means entries fall out of it, so anything able to influence ranking can **suppress** — pushing a confirmed guardrail out of the window without injecting a single token. Hence the **reserved floor**: human-ratified memories always ship regardless of ranking, and graph influence orders only the remainder.

**Auto-commit is gated on provenance, not merely on additiveness.** The user's own utterance auto-commits and may influence ranking; third-party content (email, newsletter, fetched page, tool output) commits **marked untrusted** and may not; the model's own inference is a conclusion (§6). None of the three reaches prompt text unaccepted. This keeps a contradictory third-party claim fully visible and fully inert — it lands, it flags the conflict, it renders, and it moves nothing the model reads.

The tiers are an optimization; **the floor is the defence**. Source classification is unreliable — users paste documents into chat constantly, and an extractor reading a pasted block is reading attacker-controlled text through a trusted channel. The floor holds even when the classification is wrong, which is why it is the part that cannot be dropped.

**Ratification is risk-weighted, because attention is the scarce resource.** Additive, low-stakes, clearly-sourced facts auto-commit. Identity-level and destructive changes stage: merges, retractions, type changes, edits to constraints or preferences. The failure to design against is notification fatigue — a review everyone clicks through is worse than no review, because everyone believes it was checked. **Review is ambient, never modal**: a queue inside the graph, pending changes drawn as ghosted diffs, acceptable in bulk.

**Entity resolution runs in three confidence bands.** Exact-identifier matches auto-commit; medium confidence proposes a merge; low-but-real confidence asserts a **`possibly-same-as` link that is a permanent representation of uncertainty**, not a to-do. Anchor resolution (§5) is what produces the bands.

**Unresolved identity is read differently by each consumer**, because they have different capacities for ambiguity. Storage always keeps two. Derivation computes **separately per entity**, since deterministic logic must never rest silently on an unratified guess — a computation over the union is a *conclusion*, not a derivation. Rendering draws two nodes with a dotted link and a merge affordance. And the agent is simply **told**: *"Diane — possibly the same person as Diana Mercer."* Suppressing one lies by omission and merging them asserts something unratified, while the model is the one consumer that reads that sentence and reasons correctly with it. A query language cannot represent "these might be the same", so the uncertainty is passed through rather than resolved before it arrives.

**Citing evidence across an unresolved identity makes the link itself evidence.** The link is an assertion like any other, so this costs nothing mechanically and buys the important property: reject the merge later and staleness propagation (§6) fires on every conclusion that leaned on it. Cross-candidate reasoning is allowed but tracked, rather than forbidden or silently wrong.

`possibly-same-as` is symmetric and **explicitly not transitive** — confidence does not compose, so it is excluded from the kernel's transitive construct. And **rejection is recorded as a fact**, not a deletion: confirming appends `sameAs`, rejecting appends `distinctFrom`. A rejection that merely deletes leaves the same similarity re-proposing the same merge forever, which is how a review queue becomes unusable. Merge proposals are the *right* place to spend the interruption budget: rare, consequential, and answerable in half a second.

**User-authored clusters are assertions, not UI state.** Dragging things into a cluster asserts a grouping in the user's world and carries provenance accordingly. Computed clusters are *proposals*. This is idea.md's "reorganize the visualization… more metadata for modelling the reality," made concrete.

**But not every gesture is a claim, and the test is contradictability.** A cluster asserts *membership* — these things belong together — which somebody can deny. A pinned coordinate asserts a *position*, which nobody can be wrong about: two people placing one node differently are not in conflict. So the log admits the first and refuses the second, and *unrepeatable* is necessary but not sufficient for a row — `retracted`, `expired` and `superseded` are all meaningless for something that cannot be false. The drag that means something becomes a claim; the drag that is placement stays furniture. Where a gesture implies an ordering rather than a grouping, capture the ordering and **discard the coordinate**: it is re-derived from the claim on every render, and it then travels between machines and carries an author.

**Give the most salient unspent channel to the least recoverable fact.** Derived facts are recomputed each render — lose one and re-parse. Stated facts are the contribution and the only thing that can be lost, so the strongest channel is spent on them: position for a stated ordering, form for a stated classification, material for whether anybody has agreed; size and text for what the parser produced. Drawing them alike is the failure this corrects — a thing you agreed was a feature must not look identical to one you rejected. Two consequences worth stating, because both were reached by argument rather than taste. Form may carry a **kind** even though a kind is derived: kinds are not contestable, and the rule governs distinguishing *states of one kind of thing*. And **absence is drawn as absence** — a node with no stated position is ungrounded, whether because nobody classified it, because its order was never stated, or because the subject it was judged against is gone. One meaning, several sources, no second mechanism.

**Onboarding is an event-storming conversation** — the agent proposes entities and events, the user corrects — so the model has a spine after twenty minutes rather than starting from an empty graph.

## 9. Governance: autonomy, exposure, trust

Palantir's fourth component, renamed. The enterprise apparatus — roles, marking taxonomies, policy engines, runtime policy evaluation — stays out, but for a narrower reason than "there is one user". The deployment is **multi-tenant, not multi-party**: one graph per person, nothing shared between them, so there is no authority structure to model. What that buys in simplicity it charges back as **tenancy isolation**: a missing owner predicate on a graph query is no longer a bug but a cross-user leak, and the rule has to be written per feature, where the resource is, by someone who remembers. That is exactly the kind of obligation forgotten silently, with nothing in a build to notice.

Three concerns remain:

**Autonomy** — what the agent may do without asking. A trust dial, not access control: Palantir's "new team member gradually granted a wider purview." Expressed as which action types commit without ratification. Per person, and durable: it is a human decision, so it belongs in the log rather than in configuration.

**Exposure** — what leaves the machine. A personal memory graph is more dangerous than the chat logs it replaces: structured, queryable and complete across relationships, health, money and private opinion — and every inference ships context to a provider. Needs one new concept: a **sensitivity level on types and subgraphs** gating what may enter a context window, reach a tool, or land in an artifact. Composes with autonomy so that a send-email tool structurally cannot leak what the graph marked private.

**Trust** — whether an assertion may be believed given its origin. The live threat is prompt injection writing false facts into memory; poisoning is worse in a graph than in a transcript because the graph is what the agent reasons *from*. Handled by provenance plus a ratified-versus-observed distinction.

**Visibility is the comprehension model, not the security model.** The graph lets a person see what the agent knows and what it may do, which no permission dialog achieves — and that is a different thing from controlling who can read it. Hosted, the graph sits on someone else's database, and the exposure paths that matter are the ones the UI cannot show: operator and database access, backups, and telemetry, where instrumented database spans carry query parameters off the machine by design. Every one of those is invisible to the person whose graph it is.

**And the open question underneath, recorded rather than assumed away.** §9's argument for why this data is dangerous is *strengthened* by hosting it: a structured, queryable, complete record of relationships, health, money and private opinion is more dangerous on a shared server than on a laptop. Local-first or self-hosted answers that; hosted requires deciding the convenience is worth it. This may end up the deciding constraint on what the product is.

## 10. Schema growth doctrine

LLMs inverted the historical bottleneck. Coyle's expert systems failed on *knowledge acquisition*; extraction is now nearly free, so **curation is the scarce resource** and the failure mode reverses: a thousand entities by Thursday with `Person`, `Contact` and `Human` all meaning the same thing.

**Instances flow bottom-up and auto-commit. Schema grows bottom-up in evidence but is ratified top-down.** The user almost never authors types in advance; a type is proposed when **the same shape appears three times** — the rule of three doing double duty as the promotion trigger.

**Seed a small core** — about six types (Person, Organization, Event, Place, Document, Topic) under schema.org names, per Coyle's advice not to reinvent existing taxonomies. An empty graph is a bad cold start: with no vocabulary the agent invents inconsistently from day one.

**Schema-versus-evidence conflicts are revision proposals, not errors.** Three observations that don't fit `Employer` mean the notion of employment is too narrow.

**Ontology refactoring is an agent chore.** The agent periodically audits the model against Palantir's anti-pattern catalogue — near-duplicate types, God Objects, Kitchen Sink imports, Misnomers, unused types — and proposes consolidations in batch.

## 11. Boundaries

**The memory is a substrate with an API, not a component inside the loop.** Two layers: a **stable generic core** (query, assert, traverse, subscribe) that survives schema change, and an **optional generated typed layer** projected from the schema — generated, never hand-authored, because the schema is itself graph data. The LLM consumes neither: it reads schema as *context* and acts through *action-type tools*.

**Anticorruption layers at every ingestion boundary.** Email, calendar, exports, other agents' output — their schemas must not leak into the ontology.

**Ingestion order**: extract → detect conflicts → dedupe → merge.

**Portability is a requirement, not a nicety.** A personal graph is a decades-scale artifact that must outlive the tool that made it. Guarantee lossless export to RDF/JSON-LD plus SHACL shapes, with a **round-trip test from the start** — untested export fidelity rots silently and is discovered only on the day it is needed.

## 12. Prior art and position

**Palantir Foundry Ontology** is the reference model: vocabulary, the four design principles, the anti-pattern catalogue, decision lineage, scenarios. Closed and enterprise-scaled; its distinctive hard part is the action layer.

**semantica** proves the substrate is buildable in open source — context graph, decision records, PROV-O provenance, bi-temporal facts, conflict detection, SHACL/OWL, explainable reasoners. **Borrow the pipeline, not the model**: its ingestion stack converges with our decisions, while its core merges conclusion with decision, lacks evidence links, has no model-actions and no negotiation surface. If used, put it behind an anticorruption layer.

**Reusable taxonomies**: schema.org, FOAF, Dublin Core.

**bacteria is the target, and it had already decided part of this.** Its accepted ADR for a Postgres-tables memory graph occupies the same ground, with the extractor and proposal queue shipped and the graph itself unbuilt. Where the two disagreed — one time axis instead of two, a disposable graph, blanket confirmation, no conclusions, no retrieval story, a single-user assumption — the reconciliation is [`dialogues/03`](../research/dialogues/03-bacteria-reconciliation.md) and the code-level mapping is [the architecture overview](README.md). Most of what is above survived contact; §9 lost a sentence that was simply false.

## 13. Deliberately deferred

Actions on the world (validation and staging beyond stub registration) · hypothetical/counterfactual branching · interval-algebra bi-temporal querying · variance checking on tool signatures · object-backed link types · OWL inference · full SHACL as a native constraint language · subtyping of object types · **temporal bounds that are themselves intervals** — "ended, but we do not know when", which past tense states constantly; v1 maps it to *unknown* and accepts losing conflicts it could have decided, erring toward under-claiming · **sharing a graph between people** — the point at which roles and marking taxonomies become necessary and this becomes a different product, foreclosed deliberately rather than drifted into.

Each is additive later. None requires restructuring what is above.

## 14. Sequencing, and the bet

Build order is part of the model, because the wrong order answers the most expensive question wrongly.

**Minimum graph → negotiation surface → traversal and vectors.** Completing the substrate first would test it under conditions guaranteed to make it fail: with no curation surface the graph fills with near-duplicate types and unmerged identities exactly as §10 predicts, and retrieval measured on *that* graph produces a false negative. The surface is also not speculative spend — it is the review queue, which is needed whether or not edges ever earn their keep.

**The bet, stated so it can be lost.** §1 claims relations between facts are what is being asked for. The cheaper rival — a vector index over confirmed facts, no edges — is genuinely plausible.

> If traversal-based retrieval does not beat recency once the graph has had real curation, the graph has not earned its keep, and the fallback is vectors over confirmed entries.

Deciding that requires replaying past runs against the memory those runs actually saw, which is why recorded time (§3) is not an accounting nicety: without it the evaluation silently grades today's beliefs and the bet can never be settled honestly.

**Amended 2026-08-28 ([dialogue 13](../research/dialogues/13-the-subject-changed.md)): the bet keeps its question and loses its kill criterion.** The reasoning above was correct while prompt injection was the graph's only consumer. It now has four — rule checking, conflict detection, the negotiation surface, and plain querying — and three of them are not retrieval, so traversal could lose outright and the graph would still be load-bearing. A vector index cannot say that one module imports another it may not, or that two people disagree about who owns a customer. In a *derived* domain the question does not arise at all: an architecture ontology is queried by someone who knows its shape, with no context budget and nothing injected.

**The replacement, because a retired kill criterion that is not replaced is how a project stops being able to be wrong:**

> If the human accepts essentially everything the agent proposes, there is no negotiation — the surface is a rubber stamp, the "shared" model is the agent's model with a signature on it, and §1 is wrong.

Measured as the proportion of proposed classifications and rules **rejected or edited** rather than waved through, with **both tails failing**: near-zero is a rubber stamp, near-total means the agent holds no model worth arguing with. It settles on weeks of a derived domain rather than months of somebody's life.

**Recorded time survives on changed grounds.** Its justification above was replay for the bet; its reason now is decision lineage — *which rules were stated when this exception was accepted* — which every domain needs. Stated explicitly so it is not later read as orphaned machinery.
