# Glossary

> Shared vocabulary — our ubiquitous language (see [05](analysis/05-ddd-article.md)). Terms are refined as meanings are agreed in `dialogues/`. Source numbers refer to `analysis/`.

## Core

| Term | Working definition | Source(s) |
|------|--------------------|-----------|
| Ontology | "A formal specification of a shared conceptualization" (Gruber, 1993): an explicit model of a domain's reality — its entities, relationships, and the operations over them. Palantir framing: the nouns and verbs of the business, modeling how reality actually operates, not how source systems structure it. | 01, 02, 03 |
| Neurosymbolic system | Probabilistic neural components (LLMs) combined with a symbolic layer (ontology + rules + reasoner); the symbolic side keeps the LLM inside guardrails. | 01 |
| Digital twin | The ontology as a live semantic+kinetic representation of the modeled reality. | 02, 03 |
| Decision-centric model | Every operational decision decomposed as **data + logic + action + security**; the ontology integrates all four. | 02, 03 |
| Shared mental model | The alignment between human and agent (or human and human) about what exists and how it relates; DDD's ubiquitous language and Gruber's "shared conceptualization" name the same thing. The graph UI is where it is negotiated. | idea.md, 01, 05 |

## Meta-model (type system)

| Term | Working definition | Source(s) |
|------|--------------------|-----------|
| Object type / object | Schema of a real-world entity or event / a single instance. | 03 |
| Property / property value | Schema of a characteristic / its value on an object. | 03 |
| Link type / link | Schema of a relationship between two object types / an instance. | 03 |
| Action type | Schema of a set of changes (edits to objects/values/links) applicable as a unit, including side effects — the "kinetic" verbs. | 03 |
| Function | Code-based logic natively integrated with the ontology (objects in/out); "logic attached to the semantic object". | 02, 03 |
| Interface | Describes the shape+capabilities shared by object types → polymorphism; multi-inheritance, multi-level. Capability-focused (Schedulable, Inspectable). | 03, 04 |
| Struct property | Multi-field property value carrying metadata (source, author, time) alongside the value. | 04 |
| Reducer | Rule that surfaces the relevant value from a multi-valued (historical) property, e.g. most-recent. | 04 |
| Derived property | Property computed declaratively from linked objects; keeps data normalized. | 04 |
| Object-backed link | A relationship implemented by an object (n-ary/reified relation), traversable as a plain link when its properties don't matter. | 04 |
| Entity resolution | Detecting and merging duplicate entities while preserving both observation sets and their provenance. | 04, 09 |

## Dynamics & lineage

| Term | Working definition | Source(s) |
|------|--------------------|-----------|
| Decision data / decision lineage | First-class record of decisions/conclusions: context, options evaluated, chosen outcome, data version, actor. Fuel for learning and agent memory. **We split this in two — see Conclusion and Decision below.** | 03, 09 |
| Scenario (staging) | A sandboxed branch of the ontology where proposed changes are explored/simulated before commit. | 03 |
| Domain event | Past-tense record of a meaningful occurrence, named in the ubiquitous language (OrderCreated). | 05 |
| Event sourcing | State as an append-only sequence of domain events; current graph derived from the log. | 05 |
| Bi-temporal fact | Fact carrying both *valid time* (when true in the world) and *recorded time* (when learned). | 09 |
| Provenance | Per-assertion record of origin (source, extractor, confidence, time); W3C PROV-O is the standard. | 04, 09 |
| Conflict detection | Contradicting facts are flagged and resolved by strategy (credibility, recency, voting), never silently overwritten. | 09 |

## Design principles (priority order per Palantir)

| Term | Working definition | Source(s) |
|------|--------------------|-----------|
| Domain-driven design (DDD) | Model the real world, not the source data. Strategic side: bounded contexts + ubiquitous language. | 03, 04, 05 |
| Bounded context | A semantic boundary within which each term has exactly one meaning. | 05 |
| Ubiquitous language | The negotiated shared language of the modeling team, directly reflected in the model. | 05 |
| Don't repeat yourself (rule of three) | One canonical representation per concept; three duplicates ⇒ refactor. Justified as context management for agents. | 03, 04 |
| Open/closed | Core types stable (closed to modification), extension via linked types and interface implementations (open). | 03, 04, 06 |
| Composition over inheritance | "Has-a" over "is-a"; capabilities compose via interfaces; avoids subtype explosion. Inheritance ≈ strongest coupling; ABCs-as-interfaces reduce coupling. | 03, 04, 06 |
| Variance (producer extends, consumer super) | Covariance: producers/return-types may narrow. Contravariance: consumers/argument-types may widen. Mutable containers: invariant. The type laws that make interface-targeted workflows plug-and-play. | 04, 07 |
| Liskov substitution principle | A subtype must be usable wherever its supertype is expected — the contract behind polymorphism. | 07 |
| Generic (vs interface) | Parameterized template for structure sharing *without* substitutability intent. | 07 |
| Anticorruption layer | Translation layer that keeps an external schema from contaminating your model. | 05 |

## Anti-patterns (short list)

Kitchen Sink (1:1 dataset mirroring) · God Object · System/Department Silos · Golden Hammer · Action Sprawl · Time Machine · Misnomer · subtype explosion (`SchedulableBuilding`). — 03, 06

## Our own vocabulary (decided in dialogue 01)

Terms coined or narrowed for this project. Sources are in [`dialogues/01-initial-questions.md`](dialogues/01-initial-questions.md); the model is in [MENTAL-MODEL.md](../architecture/memory-graph.md).

| Term | Definition | Decided in |
|------|------------|-----------|
| Assertion | The unit of the append-only log: a claim about the world with provenance, valid time and recorded time. Addressable, so conclusions can cite it as evidence. | Q7, Q9 |
| Model-action | An action whose effects are entirely inside the graph (create entity, link identities, retract a conclusion). First-class in v1, reversible, always carries actor + timestamp + reason. | Q1 |
| World-action | An action with external side effects (send email, call API). Deferred: registered as a stub, validated later. | Q1 |
| Negotiation surface | The graph UI as the place where human and agent jointly propose, contest and ratify the model. The project's differentiator. | Q5, Q6 |
| Ratification | User acceptance of a staged change. **Risk-weighted**: additive facts auto-commit, identity-level and destructive changes stage. | Q6 |
| Interruption budget | The finite supply of user attention. Spending it badly (approving every extracted entity) causes notification fatigue and makes review theatre. | Q6, Q8 |
| Approval staging | Proposed actions meant to be committed after review. v1. | Q6 |
| Hypothetical staging | A named set of proposed actions the graph is viewed *through* and then discarded — counterfactual reasoning. v2. | Q6 |
| Conclusion | A **belief** with subject links, mandatory evidence links, confidence and prose. Revisable: derived → active → stale → superseded/retracted. | Q4 |
| Decision | A **choice**, linked to the conclusions it rested on and actions it triggered. Immutable once executed; evaluated in hindsight via a separate object. | Q4 |
| Staleness propagation | When an assertion is revised or retracted, walking evidence links to mark dependent conclusions stale. The operation that justifies the conclusions layer. | Q4 |
| `possibly-same-as` | A permanent, first-class representation of unresolved identity uncertainty — not a to-do item. Read differently by each consumer: storage keeps two, derivation computes separately, rendering draws a dotted link, the agent is told the ambiguity in prose. Symmetric, not transitive. Citing evidence across it makes the link itself evidence. | Q8, F5 |
| Constraint kernel | The six enforced constructs: functional, enumerated range, domain/range, disjoint, inverse, transitive. Each must be explainable in one sentence. | Q10 |
| Autonomy | What the agent may do without asking — a trust dial, not access control. | Q3 |
| Exposure | What may leave the machine; a sensitivity level on types/subgraphs gating context windows, tools and artifacts. | Q3 |
| Trust (of an assertion) | Whether a claim may be believed given its origin; provenance plus a ratified-vs-observed distinction. Defends against memory poisoning. | Q3 |
| "Is it a thing?" test | The promotion rule: a thing → object; a bundle of fields about something else → struct; what-you-can-do-with-this → interface. | Q9, Q14 |
| Ontology refactoring chore | Periodic agent-run audit against the anti-pattern catalogue, proposing consolidations in batch. | Q13 |

## Vocabulary from the bacteria reconciliation (dialogue 03)

Terms added when the model was reconciled against the target codebase. Reasoning in [`dialogues/03-bacteria-reconciliation.md`](dialogues/03-bacteria-reconciliation.md).

| Term | Definition | Decided in |
|------|------------|-----------|
| Assertion log | The durable middle layer: claims with provenance, both time axes, actor and ratification status. Not regenerable from the transcript, because non-deterministic extraction and human decisions went into it. | R2 |
| Projection | The disposable layer folded from the log — current-state graph, embeddings, derived properties, staleness marks. Disposable because its *inputs* are durable, not because it is cheap. | R2 |
| Determinism test | The rule deciding which layer something belongs to: *can it be regenerated deterministically from what is kept?* If a model call or a human decision went into it, it is durable. | R2 |
| Two surfaces | Writing to the graph and contributing text to a prompt are distinct acts, governed differently: graph writes are risk-weighted, prompt text is confirmed only. Collapsing them forces a false choice between notification fatigue and memory poisoning. | R3 |
| Reserved floor | Human-ratified memories always ship regardless of ranking. The defence against **suppression** — pushing a confirmed guardrail out of a bounded context window without injecting a token. A condition of the two-surface split, not an enhancement. | R3 |
| Trust tier | Auto-commit gated on provenance class: the user's own utterance, third-party content (committed *marked untrusted*), or the model's own inference. An optimization of the interruption budget; unreliable, because pasted documents arrive through a trusted channel. | R3 |
| Anchor resolution | Getting from a raw message to a starting node — exact identifier, then lexical/alias, then vector similarity. What makes traversal possible; also the missing implementation of §8's entity-resolution bands. | R5 |
| Comprehension model | What the visible graph actually provides: a person can see what the agent knows and what it may do. Explicitly *not* the security model, since operator access, backups and telemetry are invisible to it. | R6 |
| Open bound / unknown bound | Two distinct end states the model originally collapsed into `[?..]`. **Open** = has not ended, true as of now (infinity sentinel); **unknown** = may or may not have ended (null). Two open-ended intervals definitely overlap, which is what makes a contradiction between current claims decidable. | E3 |
| Defeasible inference | A deterministic rule whose output further evidence can defeat — the commonest being a constraint plus one known boundary implying an unknown one. Not a derivation, because it is *assumed* rather than *entailed*; recorded as a conclusion with `derivedBy` naming the rule. | E1 |
| Explained conflict | An undecided conflict with an active conclusion accounting for it. The badge turns from a question into a citation with a confidence, rather than vanishing. Retracting the conclusion returns it to *possible*. | E1 |
| Possible conflict | A constraint violation that cannot be decided because a bound is unknown. Rendered as such, never blocking, resolved by learning one date. The time analogue of `possibly-same-as`. | E4 |
| Kill criterion | The stated condition under which the graph is abandoned: traversal-based retrieval failing to beat recency on a curated graph, with vectors-over-confirmed-entries as the fallback. | R7 |
