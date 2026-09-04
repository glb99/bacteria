# Analysis 05 — What Is Domain Driven Design (DDD)? (Mert Özler)

Source: [`sources/05-ddd-article/`](../sources/05-ddd-article/raw.md)

## Summary

A distilled tour of Evans/Vernon DDD, split into strategic and tactical design.

**Strategic design** (must come first):
- **Bounded Context** — a *semantic* boundary: inside it, every term has one specific meaning. Analogy: national language borders. One team per context; source code and schema separated along it. A context developed as the company's key initiative is the **Core Domain**.
- **Ubiquitous Language** — the shared language between domain experts and developers, emerging from a feedback loop that "creates a united mental model within the team"; it directly shapes design and code (every business action ↔ a function).
- Focus on **business complexity, not technical complexity**; developers must model *with* domain experts, not from documents.
- **Subdomain** — subset of the business domain; ideally 1:1 with a bounded context.
- **Context Mapping** — the catalogue of relationships between contexts: Partnership, Shared Kernel, Customer–Supplier, Conformist, **Anticorruption Layer** (a translation layer isolating your language from an upstream one), Open Host Service, Published Language, Separate Ways.

**Tactical design**:
- **Entity** — an individual thing with unique identity, usually mutable.
- **Value Object** — immutable, identity-free, compared by attributes; quantifies/describes entities.
- **Aggregate** — cluster of entities under an aggregate root; a **transaction-consistency boundary**.
- **Domain Event** — record of a business occurrence, named in past tense in the ubiquitous language (OrderCreated); saved atomically with the aggregate (outbox pattern), then published to interested contexts.
- **Event Sourcing** — the aggregate's state *is* its append-only sequence of domain events.
- **Event Storming** — a workshop technique: model the business by its events and processes (sticky notes on a wall), experts + developers together.

## Relevance to the project

- **Ubiquitous language ≈ the ontology's vocabulary.** DDD says the shared mental model *is* a negotiated language between parties; idea.md says the memory graph is the shared mental model between human and agent. Fusing the two: bacteria's ontology is the ubiquitous language of the human–agent team, and the graph UI is where it gets negotiated. (This is the "interfaces let you think deeper" thread the user flagged.)
- **Bounded contexts warn against one global graph.** The same word means different things in different areas of a user's life/work ("project", "client"). A single undifferentiated memory graph would blur meanings — DDD suggests the memory may need context/namespace boundaries, with explicit mappings between them. This also matches idea.md's "reorganize the visualization (hierarchies, clusters) as more metadata": clusters may literally be bounded contexts.
- **Domain events + event sourcing** offer the mechanics for memory dynamics: the memory's state as an append-only log of semantic events ("EntityObserved", "ConclusionReached", "RelationRevised") from which the current graph is derived. This cleanly implements the temporality and provenance needs from [04](04-palantir-advanced-ontology.md) and the decision lineage from [03](03-palantir-ontology-docs.md).
- **Anticorruption layer** is a useful pattern for ingesting external sources (files, apps, other agents' outputs) into the ontology without letting their schemas contaminate it — the "model reality, not systems" rule ([03](03-palantir-ontology-docs.md)) operationalized at the boundary.
- **Event storming** is basically a human ritual for bootstrapping an ontology — the human+agent equivalent could be a guided conversation where bacteria proposes entities/events and the user corrects, exactly the dialogue-driven modeling flow idea.md wants.

## Connections to other sources

- DDD is principle #1 in both Palantir sources ([03](03-palantir-ontology-docs.md), [04](04-palantir-advanced-ontology.md)); this article supplies the parts Palantir doesn't foreground: bounded contexts, ubiquitous language as *process*, aggregates, events.
- Gruber's "shared conceptualization" ([01](01-agentic-ontologies-coyle.md)) ↔ ubiquitous language: both define knowledge as an *agreement between parties*, not a data structure.
- Event sourcing ↔ Palantir's decision lineage and multi-valued temporal properties ([03](03-palantir-ontology-docs.md), [04](04-palantir-advanced-ontology.md)) — three independent arrivals at "keep the history, derive the present".
- Aggregates (consistency boundaries) have no obvious Palantir counterpart — candidate concept for *our* model: which memory subgraphs must change atomically?

## Open questions for the human

1. Should bacteria's memory be **partitioned into bounded contexts** (work / personal / per-project…), each with its own vocabulary, with explicit context mappings — or one graph with clustering as a soft, visual-only device?
2. Are you drawn to an **event-sourced memory** (append-only semantic events, graph as a projection)? It's the strongest unification of provenance + temporality + decision lineage seen so far, but it costs implementation complexity.
3. In the human↔agent relationship, who plays "domain expert" and who plays "developer"? Presumably the human is the domain expert of their own reality and the agent is the modeler that proposes structure — do you agree with that division as a design stance?

## Provisional conclusions

- Adopt **ubiquitous language** as the framing for the ontology's vocabulary: terms in the graph must be terms the *user* actually uses, negotiated through dialogue, not agent-invented jargon.
- Keep **bounded contexts** and **domain events / event sourcing** as strong candidate concepts for the mental model; both repeatedly reinforced by other sources.
- The research repo itself should practice what it studies: `GLOSSARY.md` is our ubiquitous language; `dialogues/` is our event-storming room.
