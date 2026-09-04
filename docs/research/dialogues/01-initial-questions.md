# Dialogue 01 — Initial questions from the first ingestion pass

> Collected from analyses 01–09 (2026-08-22), grouped and deduplicated, roughly ordered by how much they shape everything else. Answer in any order/format — answers and agreed conclusions get recorded here and promoted to `MENTAL-MODEL.md`.

## A. Scope of the ontology tetrad (data / logic / action / security)

1. **Actions**: should bacteria's memory include actions as first-class objects (modeled verbs with parameters/effects, validated before execution), or is v1 data+relations+conclusions only? Note: semantica shows the substrate is commodity *except* the action layer — actions are both the hardest and the most distinctive piece. (from 02, 03, 09)
2. **Logic sources**: what are they for a personal agent — user-defined rules? saved prompts? small functions attached to entity types? Is this the seam where the conclusions-taking engine plugs in? (from 02)
3. **Security**: in scope for the mental model (what the agent may read/write/do autonomously), or deferred? (from 03)

## B. The conclusions/decision layer

4. Should decisions/conclusions be **first-class objects** linking evidence, options considered, outcome, confidence — Palantir's "decision lineage", semantica's `record_decision`? Is semantica's schema (category / scenario / reasoning / outcome / confidence + CAUSED/INFLUENCED/PRECEDENT_FOR links) good enough as the v1 shape? (from 03, 04, 09)
5. Should the memory **validate/veto** agent actions (guardrail role) or only inform them (map role)? Coyle's "police vs map" fork. (from 01)
6. Is **scenario staging** (agent proposes graph changes → human reviews → commit) part of your memory UX vision? (from 03)

## C. Substrate design

7. **Temporality**: historic-by-default (append-only observations, bi-temporal, current state derived) vs current-state with selective history? Three sources independently push append-only (04 reducers, 05 event sourcing, 07 immutability). (from 04, 05, 07)
8. **Entity resolution UX**: auto-merge, propose-merge in the UI, or keep "possibly-same-as" links? This is a key human↔agent alignment moment. (from 04)
9. **Reified relationships** (links with properties/time-spans as objects): core model from day one, or are plain edge properties enough? (from 04)
10. **Formality dial**: (a) untyped property graph, (b) typed with interfaces + informal rules, (c) checked constraints/variance like a type checker. Where is v1? And a formal constraint language (RDFS/OWL/SHACL-like) in v1 or later? (from 01, 07)
11. **Bounded contexts**: partition the memory into contexts (work/personal/per-project) with distinct vocabularies and explicit mappings, or one graph with soft visual clustering only? (from 05)
12. **W3C alignment** (PROV-O, SHACL, OWL): worth the complexity for interoperability, or pragmatic property-graph schema? (from 09)

## D. Schema growth & modeling doctrine

13. Bottom-up growth (agent harvests entities from interactions) vs top-down (user defines schema first) — which is primary? Both with what precedence? (from 01)
14. Capabilities on entities: **interfaces implemented by types** (Palantir-style), **linked facet objects** (pure composition), or both? They differ visibly in the UI. (from 06)
15. Is subtype specialization allowed at all in v1, or interfaces+composition only? (from 06)
16. Do you buy the **"SDK of your ontology"** idea — the memory exposes a typed API the rest of bacteria consumes, rather than being an internal detail of the loop? (from 02)

## E. Process / meta

17. Who is "domain expert" and who is "developer" in the human↔agent modeling relationship? Working stance: the human is the domain expert of their reality; the agent is the modeler that proposes structure. Agree? (from 05)
18. **Semantica**: build on it (or specific modules: extraction, conflicts, PROV-O export) vs use as design reference only? My lean: reference first, audit before depending. (from 09)

## Answers & agreed conclusions

- **(2026-08-22) Source 08 closed**: the Sankar keynote has no accessible transcription; the user decided to drop it. Its thesis is already covered by sources 02/03/04, so nothing is lost from the mental model.

- **(2026-08-22) Q1 — Actions: AGREED.** Actions are first-class, but the question splits in two:
  - **Actions on the model** (create entity, merge entities, assert/revise relation, record or retract a conclusion, rename a type) are first-class in v1. They are internal, reversible, and needed anyway: every graph change carries an actor (human or agent), a timestamp and a reason, which is what gives provenance, undo, and the ratification flow. Keep this set **small and general** to avoid Palantir's Action Sprawl anti-pattern.
  - **Actions on the world** (send email, write file, call API) are deferred. Each tool registers a thin `ActionType` stub — name, object types touched, read-only vs mutating — with no validation engine behind it. Results and lineage are recorded from day one; preconditions and validation switch on later once the rules layer exists (Q10), with no restructuring.
  - Consequences: scenario staging (Q6) becomes nearly free — a staged change is an action recorded but not committed. Q5 stops being binary: the memory polices model-actions from day one, world-actions later. Q3 narrows to "which action types may the agent commit without asking".

- **(2026-08-22) Q2 — Logic sources: AGREED.** Logic for a personal agent is three **declarative** tiers, attached to *types* (not instances, though instance-level exceptions are allowed) and stored as **data, not code** — arbitrary code would need a runtime and sandbox and would destroy the property that a human can read and contest the rules:
  - **Constraints** — reject illegal states (one birth date; status ∈ fixed set; employment needs a start date). Coyle's guardrails.
  - **Derivations** — compute from the graph instead of storing (days since last contact, open threads per project, stale-contact flags). Palantir's derived properties; makes the graph feel intelligent with no LLM.
  - **Preferences and definitions** — the user's own rules about their own world ("nothing before 10am", "anything from my sister is high priority", "*the project* means the most recently touched one"). **Explicitly agreed by the user: these live in the graph.** This is the real personal analog of enterprise business logic, and today it hides as unstructured prose in system prompts; as first-class objects it becomes inspectable, editable, versioned, and visible in the same surface as the facts.
  - **LLM judgments are NOT logic.** They are conclusions, recorded in the decision layer with provenance and confidence. Logic computes; conclusions record that computing happened.
  - The conclusions engine is a *consumer* of logic, not a logic source: it reads the graph, applies constraints/derivations deterministically, invokes LLM judgment only where judgment is genuinely needed, then writes a Conclusion recording which logic was applied.

- **(2026-08-22) Q3 — Security: AGREED, in scope but renamed.** Palantir's apparatus (roles, marking taxonomies, policy engines, runtime policy evaluation) stays **out** — it answers a multi-user problem bacteria doesn't have. What stays in is three concerns that the single word "security" hides:
  - **Autonomy** — what the agent may do without asking. A trust dial, not access control; Palantir's "new team member gradually granted a wider purview". Already shaped in Q1: which action types commit without ratification.
  - **Exposure** — what leaves the machine. **Explicitly agreed as v1.** A personal memory graph is more dangerous than the chat logs it replaces (structured, queryable, complete: relationships, health, money, private opinions), and every inference ships context to a provider. The boundary is which parts of the graph may enter a context window, reach a tool, or land in an artifact. Needs one genuinely new concept: a sensitivity level on types/subgraphs.
  - **Trust** — whether an assertion can be believed given its origin. The live threat is prompt injection writing false facts into memory (memory poisoning is worse in a graph than in a transcript, because the graph is what the agent reasons *from*). Handled by provenance plus a ratified-vs-observed distinction, which Q7/Q8 need anyway.
  - Compositional property worth keeping: the agent may only invoke a tool with data it is permitted to expose, so a send-email tool structurally cannot leak what the graph marked private.
  - Project-level insight: **because the graph is visible, visibility is the security model** — the user can see what the agent knows and what it may do, which no permission dialog achieves.

- **(2026-08-22) Q4 — Conclusions layer: AGREED, with semantica's schema rejected as-is.** First-class status was already implied by Q1 (`RecordConclusion` is an action) and Q2 (LLM judgments are conclusions, not logic). The shape needs three changes:
  - **Split belief from choice** (explicitly agreed by the user). A **Conclusion** is a *belief* ("Alice is probably the decision-maker at Acme") and is revisable — evidence changes, so it gets superseded or retracted; lifecycle: derived → active → stale → superseded/retracted. A **Decision** is a *choice* ("therefore email Alice not Bob") and is *history* — immutable once executed, evaluable only in hindsight via a separate linked evaluation object. Merging them (as semantica and Palantir do, both being decision-centric) makes it impossible to retract a belief without rewriting history, or to ask "what did I believe when I chose this?"
  - **Link into the graph, don't just store prose.** semantica's `scenario`/`reasoning` are free text, leaving conclusions beside the graph rather than in it — no traversal from Alice to things concluded about Alice, and invisible in the shared visual model. Keep the prose (humans need to read *why* in natural language) but add links: subject entities, supporting assertions, and the rule or LLM invocation that produced it.
  - **Evidence links are mandatory**, because they enable the one operation that justifies the whole layer: when a fact is revised or retracted, walk to every conclusion that depended on it and mark it stale. Without it this layer is an audit log; with it the memory self-corrects.
  - Keep from semantica: confidence scores, precedent search (`find_similar_decisions` — "what did I conclude last time in a situation like this"), and decision→decision causal links.

- **(2026-08-22) Q5 — Police vs map: AGREED.** The memory polices the *model* now and the *world* later (per Q1), with three graded responses rather than a binary:
  - **Reject malformed** — structural and type violations (a second birth date, an out-of-enum status, a link with wrong-typed endpoints). Coyle's catalogue is all of this kind: duplicate refund via functional property, payout to the wrong class via disjointness, invented "probably shipped" via enumerated range.
  - **Flag contradictory, don't reject** — factual conflicts land with both assertions and both provenances intact, and the contradiction becomes visible for human+agent resolution. Rationale: a system that models reality must be able to represent that reality *is* contradictory; a graph that rejects all conflict can only represent a tidied world, which is a worse model than an honest messy one.
  - **Asymmetric authority — user's explicit instruction: "negotiate with me, don't block."** The agent's writes are validated and refusable. The user's writes are never refused: a constraint violation opens a negotiation — *your rule says one employer, this says two; fix the fact or fix the rule?* Unlike Foundry, where constraints encode organizational authority, here the constraint layer is a **contestable hypothesis about the user's world**, and the user is the domain expert who can overrule it (ties to Q17).
  - **Build the validator seam now**, positioned exactly where Coyle puts it — after the action is proposed, before anything commits — so deferred world-actions route through the same place later without restructuring.

- **(2026-08-22) Q6 — Staging: AGREED.** Staging is two features on one mechanism, and the mechanism is free from Q1 (a branch is just *a set of actions not yet applied*; no separate branching subsystem):
  - **Approval staging (v1)** — agent proposes, user ratifies; actions with status `proposed` meant to be committed.
  - **Hypothetical staging (v2)** — a named set of proposed actions the graph is viewed *through* and then discarded ("what if I took that job? what if Alice isn't the decision-maker?"), letting derivations and the conclusions engine recompute against a counterfactual. This is idea.md's "reality modeling engine that guides decisions" at its most literal, deferred only because it needs branching machinery.
  - **Risk-weighted ratification (agreed).** The failure mode to design against is notification fatigue: if every extracted entity needs approval, the user ratifies nothing within a week and review becomes theatre that is *worse* than no review, because everyone believes it was checked. So: **additive, low-stakes, clearly-sourced facts auto-commit** (visible, attributed, trivially undone); **identity-level and destructive changes stage** (entity merges, retractions, type changes, edits to constraints or preferences) — the ones that are hard to undo and reshape rather than extend the model.
  - **Review is ambient, never modal** — a queue inside the graph with pending changes drawn as ghosted/diff-styled nodes and edges, acceptable in bulk; not a dialog that interrupts mid-conversation.

## C. Substrate design

- **(2026-08-22) Q7 — Temporality: AGREED, append-only.** The decisive argument is not source consensus but **internal consistency with Q4 and Q5**:
  - Q4's staleness propagation requires prior state to still exist — if a revision overwrote the old value, you cannot distinguish "this evidence changed since I concluded" from "this evidence was always thus".
  - Q5's flag-don't-reject requires a property to hold several values at once, each with its own provenance — i.e. overwriting is already not how facts enter the graph.
  - **The action log is the event log.** Q1 gave every model change an actor, timestamp and reason; append-only just means never deleting them and deriving the graph by folding them. No separate DDD "domain event" concept is needed — a *committed* action is exactly a past-tense record of what happened. Lifecycle: proposed → validated → committed → immutable log entry.
  - **Bi-temporal from day one, cheaply.** Valid time and recorded time diverge constantly in personal memory ("today I learned Alice left her job in March"), and both axes are what protect the conclusions layer from unfair invalidation — a conclusion drawn in April was reasonable *given what was known then*. Cost is two timestamps per assertion; sophisticated interval-algebra querying is deferred (retrofitting a time axis is brutal, adding queries later is easy).
  - **Non-concerns**: storage growth is negligible at personal text scale (don't optimize it); read performance is handled by materializing a current-state projection while the log stays the truth; UI burden is handled by source 04's reducers/struct-main-fields pattern — current value shown, history behind hover/expand. **Time is a lens the user can turn on, not a burden they carry.**

- **(2026-08-22) Q8 — Entity resolution: AGREED.** The three options are not alternatives but **confidence bands**, and all three are used:
  - **Exact-identifier match** (same email, same phone) → auto-commit; no judgment involved, interrupting would be noise.
  - **Medium confidence** (similar name + shared context) → propose a merge and wait.
  - **Low-but-real confidence** → assert a **`possibly-same-as` link**, agreed as a *permanent representation of genuine uncertainty*, not a to-do the agent must eventually resolve. Forcing a binary destroys information the model legitimately has; the link stays visible and resolves when new evidence arrives.
  - **Structural rule: don't merge entities, link identities.** A merge is an *action asserting `sameAs`*, never a destructive rewrite (source 04 keeps both underlying objects with their original properties and derives a unified view). With append-only from Q7 this is free, and it makes **unmerge** just a retraction. This matters because conflating two people and being unable to separate their histories is the failure that poisons a memory permanently. **Split is a first-class inverse**, available only because merging never destroyed the originals.
  - This is source 03's "separate identity from observation": an *observation* says an entity called "Diane Mercer" appeared in this email; *identity resolution* says that observation and this one refer to the same person.
  - **Merges are a good use of the Q6 interruption budget** — rare, consequential, and answerable by the user in half a second. Contrast with low-value interruptions like "is this a Person?", which the agent should just decide.

- **(2026-08-22) Q9 — Reified relationships: AGREED, deferred (possibly permanently).** Object-backed link types are not built in v1; two cheaper mechanisms cover the cases:
  - **Addressability comes free from Q7.** Q4 requires relationships to be citable as evidence, but an append-only log already gives every assertion an identity, so conclusions cite assertion IDs. No reification needed for citation.
  - **N-ary and property-rich relationships are events.** For a personal graph nearly all such cases (meetings, trips, introductions, collaborations, jobs) are events, and source 03 states an object type is the schema of a real-world entity *or event*. So model **Event as an ordinary object type with participant links** — idiomatic, and costs nothing new.
  - **Plain edge properties suffice** for genuinely binary relationships with light metadata (`since`, `role`).
  - Source 04's object-backed links are an ergonomics/query-optimization feature for mature ontologies (traverse `employee → venture` directly *or* step through `VentureStaffing`), not a modeling necessity; if the shortcut is wanted later, a derived link (Q2 derivations tier) provides it.
  - **Modeling rule to write down**: when a relationship starts wanting properties beyond a scalar or two, or a third participant appears, **promote it to an event object**. Naming this as a rule matters for Q13 — an LLM left alone will pile properties onto an edge forever.

- **(2026-08-22) Q10 — Formality: AGREED, "(b+)".** The (a)/(b)/(c) framing was broken: **schema richness and enforcement strictness are independent axes**. Prior answers already placed us at moderately rich types, strictly enforced *against the agent*, negotiable *with the user* (Q5) — a position no type checker can express.
  - **(c) is structurally unavailable**: a type checker validates against a schema fixed at authoring time, but here the agent proposes new types mid-conversation (Q13). So **the schema lives in the graph as data, evolves through actions like everything else, and validation is a runtime query, not a static check.** The schema being part of the shared model is exactly why it is contestable.
  - **Borrow the semantics of RDFS/OWL/SHACL, skip the standards.** A six-construct kernel captures ~90% of Coyle's benefit: **functional** (at most one value — the duplicate-refund class), **enumerated range** (invented values like "probably shipped"), **domain/range** on link types (wrong-typed endpoints), **disjoint** (category confusion — his payout-to-support-rep), plus **inverse** and **transitive** as cheap derivations.
  - Decisive criterion: each construct must be **explainable in one sentence**, because Q5 lets the user contest constraints and contesting requires reading. "Your rule says a person has one employer" is contestable; a SHACL shape graph is not. **Adopting the full standards would quietly break negotiability.**
  - **Variance checking deferred entirely** — source 07's rules only pay off with many tools typed against many interfaces. Keep the discipline (target interfaces, not concrete types) as doctrine without a checker.
  - Consequence for Q12: because constraints are declarative data, emitting SHACL later is serialization, not a rewrite.

- **(2026-08-22) Q11 — Bounded contexts: AGREED, one graph, no hard partitions.** The ambiguity DDD addresses is real (client/project/review mean different things in different areas of life) but bounded contexts are the wrong instrument: they exist because different **teams** own models and cannot agree — a coordination problem between people that a single user does not have. Meanwhile partitioning would destroy **cross-domain connection, which is the entire value proposition** (your climbing partner also knows your biggest client).
  - **Ambiguity → types and naming.** Distinct meanings get distinct types (`WorkClient`, `TherapyClient`), sharing an interface only if they genuinely share shape. The true DDD lesson is precision in naming, not walls.
  - **Exposure → Q3 sensitivity marks**, an *orthogonal axis*, not a partition — something can be work-related and public, or work-related and highly private.
  - **Navigation → views**: filters, clusters, saved perspectives, none of which require dividing the model.
  - **Keep the anticorruption layer unconditionally.** Email, calendar, Notion exports, other agents' output — their schemas must not leak into the ontology. This is "model reality, not systems" enforced at the boundary, and the highest-value DDD import for this project.
  - **User-created clusters are first-class assertions, not UI chrome** (user agreed). Dragging things into a cluster asserts a grouping *in the user's world*, so it carries provenance like any other model content; computed clusters (semantica's community detection) become *proposals*, and accepted ones become assertions. This is idea.md's "reorganize the visualization… more metadata for modelling the reality", made concrete.

- **(2026-08-22) Q12 — W3C alignment: AGREED, graded per standard.**
  - **PROV-O: adopt the vocabulary** (entity / activity / agent, `wasGeneratedBy`, `wasDerivedFrom`, `wasAttributedTo`). Nearly free, and it maps onto the existing design with no friction: assertions are entities, actions are activities, human-or-agent are agents, `wasGeneratedBy` links an assertion to the action that created it, `wasDerivedFrom` *is* Q4's evidence link. Some provenance vocabulary is needed anyway; theirs is better than one invented from scratch.
  - **SHACL: export target, not foundation** (per Q10).
  - **OWL: skip.** Its value is model theory and inference; Q10's six-construct kernel already covers every example Coyle actually demonstrated, and full reasoning is heavy for no personal-scale payoff.
  - **Native representation: pragmatic property graph.** Everything committed to is awkward in triples — n-ary events need blank-node reification, per-assertion provenance needs named graphs or RDF-star, bi-temporality gets clumsy — and natural in LPG. semantica hedging via polyglot storage is telling.
  - **The real requirement is portability/longevity, not compliance.** Regulators are semantica's market; a personal graph is a decades-scale artifact that **must outlive the tool that created it**. That argues for guaranteed *lossless export* (RDF/JSON-LD + SHACL shapes) as a deliverable, so the standards cost a serializer rather than an architecture. **Build a round-trip test from the start** — untested export fidelity rots silently and is only discovered on the day it is needed.

## D. Schema growth & modeling doctrine (answers)

- **(2026-08-22) Q13 — Schema growth: AGREED, a ratchet.** Coyle's history lesson (top-down expert systems failed to scale, causing the AI winter) does **not** transfer cleanly: what failed was the *knowledge acquisition bottleneck*, and **LLMs invert it — extraction is now nearly free, so the scarce resource is curation**, the same budget Q6 protects. The new failure mode is the opposite of the old one: a thousand entities by Thursday, with `Person`/`Contact`/`Human` types all meaning the same thing.
  - **Instances flow bottom-up and auto-commit** (high volume, low stakes, per Q6).
  - **Schema grows bottom-up in evidence but is ratified top-down.** The user should almost never author types in advance; a type is **proposed when the same shape appears three times** — the rule of three doing double duty as the schema-promotion trigger. Keeps the model honest to the user's actual life while passing every structural change through them. **User confirmed they are comfortable with the agent proposing schema changes.**
  - **Seed a small core** (~6 types: Person, Organization, Event, Place, Document, Topic) using **schema.org names**, per Coyle's "don't reinvent the wheel". An empty graph is a bad cold start — with no vocabulary the agent invents inconsistently from day one. Free consistency plus free alignment for Q12's export.
  - **Conflict precedence follows Q5**: an observation that doesn't fit a user-defined type still lands, flagged as not fitting; the user wins on *meaning*, the evidence is not discarded. And **a conflict between schema and accumulated evidence is itself a proposal to revise the schema** — three observations that don't fit `Employer` means the notion of employment is too narrow.
  - **Feature named: ontology refactoring as an agent chore.** Since curation is scarce and the agent has unlimited patience, it periodically audits the model against Palantir's anti-pattern catalogue (near-duplicate types, God Objects, Kitchen Sink imports, Misnomers, unused types) and proposes consolidations in batch, arriving as ambient review rather than interruptions.

- **(2026-08-22) Q14 — Capabilities: AGREED, three mechanisms with one decision rule.** The question was mis-posed: Palantir's interfaces and ArjanCodes' composition are **not rivals** — multi-inheritance interfaces *are* Palantir's composition mechanism (Arena implements Building *and* SchedulableResource instead of a contrived `SchedulableBuilding`); both sources fight the same enemy, the subtype explosion. A third option was missing from the original question: **struct properties** (source 04).
  - **Struct property** — grouped data that isn't a thing (address, contact details). Shows as grouped fields in the node inspector, carries its own provenance metadata, adds no visual noise.
  - **Interface** — capabilities and contracts (`Schedulable`, `Contactable`, `Locatable`). Type-level, invisible in the instance graph; what tools and workflows target per Q10. In the UI: a badge and a filter ("show me everything schedulable").
  - **Linked object** — reserved for genuine real-world entities/events (`Employment` with employer/role/dates, a meeting, a trip). Same promotion test as Q9, which keeps the two rules coherent.
  - **Decision rule: "would you point at it and call it a thing?"** Thing → object. Bundle of fields about something else → struct. What-you-can-do-with-this → interface.
  - **Decisive argument is visual and specific to this project**: if every Person carries `ContactInfo`/`EmploymentInfo`/`PreferencesInfo` satellite nodes, the graph fills with structural plumbing instead of things that exist in the user's world — "model reality, not systems" violated in the one place the user actually looks. Three visual treatments (badges / grouped fields / nodes) match three semantic roles and keep the graph legible as it grows.

- **(2026-08-22) Q15 — Subtyping: AGREED, none.** No is-a between object types in v1; taxonomy goes through interfaces.
  - **Why it matters more here than in ordinary software**: Q13 lets the agent propose types, and LLMs are drawn to taxonomies — allow subtyping and `Person → Colleague → CloseColleague → FormerCloseColleague` arrives one reasonable-looking proposal at a time. Forbidding it forecloses the specific failure mode the schema-growth policy creates.
  - **Nothing is lost.** Source 04's *taxonomic identity interfaces* (`MilitaryAsset` implemented by Aircraft/Vessel/GroundVehicle, "useful for drilldown investigations or aggregation workflows") cover the need: `Dog implements Animal` still answers "show me all animals". Interfaces being multi-level and multi-inheritance can express any taxonomy a subtype chain could, but composably — Animal + Pet + Companion with no combinatorial node in the middle. Property inheritance is covered since an interface describes an object type's shape and can require properties.
  - **Leftover case** — types sharing fields but genuinely not the same kind of thing — uses source 03's **shared properties**, the graph equivalent of source 07's "if the parent exists only for code sharing, make it a generic, not a supertype".
  - **Meta-principle worth keeping for all of v1 scope**: adding subtyping later is additive and safe; removing it after the agent has built hierarchies on it is not. **When a decision is asymmetric, take the reversible side.**

- **(2026-08-22) Q16 — Ontology as SDK: AGREED.** idea.md already said this in different words — "the first **substrate** on which some conclusions-taking engine could work" is platform language, not feature language. Either bacteria has a memory component, or bacteria is an application over a memory substrate; the second makes the memory outlive the agent (Q12), makes it valuable as open source, and stops the five known consumers (loop, UI, conclusions engine, validator, exporter) coupling to internals.
  - **Generated, not authored.** Because the schema lives in the graph as data (Q10), typed accessors are *projected* from it, so the API tracks the model instead of drifting.
  - **Two layers, to resolve the tension with Q13's continuous schema growth**: a **stable generic core** (query, assert, traverse, subscribe) that does not change when the schema changes — what the UI and loop use — plus an **optional generated typed layer** for code that wants ergonomics.
  - **The agent doesn't want the SDK at all.** An LLM has no compile step: it reads the schema at runtime as *context* and acts through *tools*. Those tool definitions are exactly Q1's action types — Palantir states actions "can be automatically surfaced as tools for all types of agents". So action types serve simultaneously as the model's verbs, the validator's units, and the agent's toolset.
  - Three consumers, three interfaces: schema-as-context + action-tools (LLM), generated types (deterministic code), generic query/subscribe (UI).
  - **Caution**: don't design the API up front for imagined consumers; derive it from the real ones and let it harden as they stabilize.

## E. Process / meta (answers)

- **(2026-08-22) Q17 — Roles: AGREED, with three refinements.** The user is the domain expert of their own reality; the agent is the modeler that proposes structure.
  - **The asymmetry isn't total**: the agent also *observes* domain facts the user hasn't articulated (you always reschedule with this person; these two projects share a hidden dependency). But it never becomes the authority on **meaning**. Division: **the agent observes, the user adjudicates.**
  - **DDD's process warning is the real prize**: both parties "should avoid the tendency for documents to speak for them", and the best ubiquitous language emerges in a feedback loop. So the ontology must never be built silently and presented as finished — **the feedback loop is the product**, and Q5/Q6 are that loop made concrete. An independent source arriving at the project's central thesis.
  - **Event storming becomes an onboarding ritual**: a guided conversation where the agent proposes entities and events and the user corrects, pairing with Q13's six-type seed so the model has a spine after twenty minutes instead of starting empty.
  - **Doctrine: never require the user to think like an ontologist.** The reason constraints must be readable sentences (Q10), clusters are drag-and-drop (Q11), review is ambient (Q6). The user brings domain truth; modeling vocabulary stays the agent's problem.

- **(2026-08-22) Q18 — Semantica: AGREED, "borrow the pipeline, not the model."** Sharpened from the original "reference first, audit before depending" now that the other 17 answers exist.
  - **Divergence is at the core, not the edges**: semantica merges decision and conclusion (Q4 splits them); its causal links are decision→decision with no evidence links, making Q4's staleness propagation impossible in its schema; it has no actions on the model (Q1), no staging or negotiation surface (Q5, Q6), and generates OWL *from* data rather than treating schema as living graph content (Q10, Q13). Building on its `ContextGraph` means fighting its decision model exactly where bacteria's differentiation lives.
  - **The ingestion pipeline is genuinely good and independently convergent** with our decisions: conflict detection with source credibility ↔ Q5's flag-don't-reject; blocking + semantic dedup ↔ Q8's confidence bands; PROV-O ↔ Q12. **Adopt the ordering regardless of the code**: extract → detect conflicts → dedupe → merge.
  - **Cautions**: the README admits the Rete matcher is "intentionally simple" (breadth over depth where depth is wanted); the repo was committed to the same day it was cloned (churn risk for a dependency).
  - **Resolution: if used, put semantica behind an anticorruption layer** (Q11) — an external source whose schema must not leak into the ontology; take its extraction output, translate at the boundary, stay free to swap or drop it.

---

**All 18 questions answered 2026-08-22.** Several answers were *forced* by earlier ones rather than chosen freely (Q7 by Q4+Q5; Q9 by Q7; Q10 by Q5+Q13), which is evidence the model is coherent rather than a pile of preferences. Promoted to [`MENTAL-MODEL.md`](../../architecture/memory-graph.md) the same day.

---
