# Analysis 02 — Palantir Ontology Overview

Source: [`sources/02-palantir-ontology-overview/`](../sources/02-palantir-ontology-overview/raw.md)

## Summary

Palantir's 5-minute canonical pitch for the ontology as the core of **decision-centric systems**.

1. **Ontology = the nouns and verbs of your business** [00:00]: plants, warehouses, customers, shipping — modeled as *how the business actually operates*, not how the underlying IT systems happen to structure it. This inversion (model reality, not systems) is the central move.
2. **Three components needed for decisions** [00:42]: **data** (current state of the business), **logic** (how to think about those things), **actions** (what you can do to affect the real world).
   - *Data sources*: connectors to any enterprise system; data is virtualized/pulled in and becomes part of the ontology.
   - *Logic sources* [01:23]: anything from Excel rules to ML models, forecasts, third-party optimizers — crucially, the logic is **attached to the semantic object** ("the logic associated with how to think about that warehouse"), not floating in a separate app.
   - *Systems of action* [02:05]: write-backs modeled as actions on the ontology (e.g. create an SAP stock-transfer order), so acting on the model acts on reality.
3. **Digital twin** [02:47]: data + logic + actions together = a rich digital twin of the operating business; workflows and analytics become by-products.
4. **LLMs get context, not just data** [03:28]: generative models reason over the ontology — they can read state, call deterministic logic, and drive actions — because the ontology supplies *the context of how the business operates*, which the LLM was never trained on.
5. **Ontology SDK** [04:11]: the ontology is exposed as a typed SDK ("an SDK of your business") so any app or integration works with domain objects directly. Goal: humans and AI working together *on the ontology*, automating more over time.

## Relevance to the project

- The **data / logic / actions triad** is the strongest structural template so far for bacteria's memory: not just entities+relations (data), but attached reasoning procedures (logic) and executable operations (actions). A memory that only stores facts is one-third of an ontology in this sense.
- "**Context, not just data**" is precisely the memory-system argument: the agent's LLM lacks the user's world model; the ontology is the vehicle for supplying it. This matches idea.md's shared-mental-model motivation almost word for word.
- The **ontology SDK** idea suggests bacteria's memory should have a programmatic, typed interface — the graph is not just visualized, it is *the API* other components (including the conclusion engine, the UI, other agents) build against.
- "Model how the business actually operates, not how the systems need it" → for personal/agent memory: model the user's reality, not the storage format (no schema leaking chat-log structure into the ontology).

## Connections to other sources

- Extends [01 — Coyle](01-agentic-ontologies-coyle.md): Coyle's ontology is graph + inference guardrails; Palantir adds the **action** dimension (Coyle only gestures at "no side effects until validated" — Palantir models the side effects themselves as first-class ontology citizens).
- The "logic attached to the semantic object" is exactly DDD's entities-with-behavior vs anemic models (source 05) and the domain-as-code idea (source 08).
- Actions as modeled, validated operations ↔ Coyle's validator; the two compose: Palantir defines *what* actions exist, Coyle's layer checks *whether a specific action instance is legal*.

## Open questions for the human

1. Should bacteria's memory include **actions** as first-class objects (things the agent can do, modeled in the graph with their allowed parameters/effects), or is v1 scope data+relations only?
2. "Logic sources" for a personal agent — what would they concretely be? User-defined rules? Saved prompts? Small functions? Is this the seam where your "conclusions-taking engine" plugs in?
3. Do you buy the "SDK of your ontology" idea — i.e., the memory graph should expose a typed API that the rest of bacteria consumes, rather than the memory being an internal detail of the agent loop?

## Provisional conclusions

- Adopt the **data / logic / action** triad as the reference decomposition for the memory system's scope discussions — even if v1 implements only "data", name the other two as explicit future layers.
- The ontology is an **interface, not a database**: plan for programmatic access (SDK-like) plus the visual graph UI as two views over the same model.
