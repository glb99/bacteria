# Analysis 09 — semantica

Source: [`sources/09-semantica/`](../sources/09-semantica/source.md) (README + ARCHITECTURE verbatim; code explored from a shallow clone)

## Summary

A self-hosted, MIT-licensed Python stack marketed as "the open-source Palantir for AI agents". Its pitch: agents that store embeddings store *similarity, not meaning*; semantica sits under the LLM/vector store/agent framework as a **deterministic** infrastructure layer (no LLM needed for graph construction, reasoning, or provenance).

Pipeline (per ARCHITECTURE.md): sources → ingest → parse → normalize → split (entity/relation/ontology-aware chunking) → extract (NER, relations, events, triplets) → **conflict detection** → **deduplication** → knowledge graph → intelligence layer (**ontology · reasoning · provenance · decisions**) → polyglot storage (RDF stores + labeled property graphs + vector stores) → export/visualize/REST/MCP/CLI.

The concepts most relevant to us:

- **Context Graph**: everything the agent knows/decides/reasons about as first-class queryable nodes; "answers *what is connected, why, and how* instead of *what is similar*". `AgentContext` wraps it with a store/retrieve API for agent memory.
- **Decision Intelligence**: `record_decision(category, scenario, reasoning, outcome, confidence)` creates a permanent graph node; `add_causal_relationship()` with typed edges (CAUSED / INFLUENCED / PRECEDENT_FOR); `trace_decision_chain()`, `find_similar_decisions()` (precedent search), `analyze_decision_impact()`, `check_decision_rules()` (policy gate). Lifecycle: record → link → query → govern → audit-export.
- **Provenance**: W3C **PROV-O** on every fact/relationship; exportable audit trails.
- **Temporal**: **bi-temporal facts** (valid time vs recorded time), point-in-time snapshots (`state_at("2024-01-01")`), Allen interval algebra.
- **Conflicts & dedup**: conflicting facts flagged (not silently overwritten) with resolution strategies (credibility-weighted, most-recent, voting) and source-credibility tracking; entity resolution via blocking + semantic dedup with provenance-preserving merges.
- **Ontology module**: OWL generation *from data* (infer classes/properties), SHACL validation, SKOS vocabularies — i.e. bottom-up schema induction plus formal constraints.
- **Reasoning**: forward chaining, Rete, Datalog, SPARQL with `ExplanationGenerator` producing step-by-step justifications. (README admits the Rete matcher is currently simplistic.)
- **Multi-agent shared context** (Agno/CrewAI integrations): one graph as the shared intelligence layer across a team of agents.
- **Explorer**: browser workbench for graph/ontology/timeline visualization.

Standards worth noting: RDF/OWL/SHACL/SKOS/PROV-O (W3C) alongside labeled property graphs — it deliberately keeps both worlds (RDF for semantics/compliance, LPG for traversal ergonomics).

## Relevance to the project

- **Existence proof + vocabulary check**: nearly every concept our other sources converged on already ships here — decision lineage ([03](03-palantir-ontology-docs.md)) → Decision Intelligence; guardrails/validation ([01](01-agentic-ontologies-coyle.md)) → SHACL + policy rules; entity resolution & temporality ([04](04-palantir-advanced-ontology.md)) → dedup + bi-temporal facts; append-only/derived-present ([05](05-ddd-article.md), [07](07-python-generics.md)) → snapshots and recorded-vs-valid time. Our mental model is not exotic; it's implementable.
- **Gap that matters for bacteria**: semantica targets *enterprise compliance* (regulators, audit). Bacteria's goal is a *shared human↔agent mental model* — the visualization/negotiation UX (proposing entities, ratifying conclusions, reorganizing hierarchies) is exactly the part semantica does **not** center (its Explorer is an inspection tool, not a negotiation surface). That's our differentiation.
- **Reuse candidates** (as library or as reference design): extraction→conflict→dedup ordering; `record_decision` schema (category/scenario/reasoning/outcome/confidence); PROV-O for provenance; bi-temporal fact model; the "no LLM required for the substrate" stance (determinism below, probability above — Coyle's split made architectural).
- **Caution**: the README oversells in places (own admission on Rete; breadth over depth is likely). Treat as a quarry of parts and patterns, not a foundation to bet on without a code-level audit of the specific modules we'd use.

## Connections to other sources

- Implements Coyle's neurosymbolic guardrail stack ([01](01-agentic-ontologies-coyle.md)): graph + RDFS/OWL-like constraints (SHACL) + rule reasoners, deterministic and explainable.
- Its Context Graph ≈ Palantir's ontology minus action types: notably **actions/write-back are missing** — no "systems of action" ([02](02-palantir-ontology-overview.md)). Decisions are recorded, but effects on external systems are out of scope. Confirms the action layer is the hardest/most distinctive part of the Palantir model.
- Bi-temporal + snapshots ↔ [04](04-palantir-advanced-ontology.md) reducers and [05](05-ddd-article.md) event sourcing.
- "One shared context graph across every agent" ↔ idea.md's shared-reality concept extended to agent teams.

## Open questions for the human

1. **Build on vs learn from**: should bacteria depend on semantica (or parts: extraction, PROV-O export, conflict detection), or build its own substrate and use semantica only as a design reference? My lean: reference first, audit specific modules before any dependency.
2. Semantica has no **action types** (Palantir's kinetics). Does that confirm your scope for bacteria v1 (memory = data+conclusions, actions later), or do you see actions as the differentiator worth building early?
3. Their `record_decision` schema (scenario / reasoning / outcome / confidence + causal links) — good enough as the v1 shape of your "conclusions" objects?
4. RDF-standards alignment (PROV-O, SHACL, OWL) buys interoperability at complexity cost. For a personal agent, do we care about W3C compatibility, or is a pragmatic property-graph schema enough?

## Provisional conclusions

- The project's technical risk is low — every substrate concept has a working open-source referent. The **novel work is the shared-mental-model interface** (graph as negotiation surface between human and agent), which nobody in our source set has built.
- Adopt semantica's pipeline ordering (extract → conflict-check → dedupe → merge) as the default mental model for how observations enter the memory.
- Keep "deterministic substrate, probabilistic reasoning on top" as an explicit architectural principle.
