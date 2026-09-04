# Analysis 03 — Palantir Foundry Ontology documentation

Source: [`sources/03-palantir-ontology-docs/`](../sources/03-palantir-ontology-docs/raw.md)

## Summary

The authoritative vocabulary and design doctrine. Five pages ingested; the essentials:

**Overview.** The Ontology is "an operational layer for the organization", a digital twin containing **semantic elements** (objects, properties, links) and **kinetic elements** (actions, functions, dynamic security).

**Core concepts** — the type system:
- **Object type** (schema of a real-world entity or event) / **object** (instance) / **object set** (collection).
- **Property** / property value; **shared property** (reused across object types).
- **Link type** (schema of a relationship) / **link** (instance).
- **Action type**: the schema of a *set of changes* a user can apply at once, including its side effects. Change is modeled, not ad-hoc.
- **Function**: code logic natively integrated with the ontology (objects in/out), used by actions and apps.
- **Interface**: describes the shape and capabilities of object types → polymorphism.
- Dataset analogy: dataset→object type, row→object, column→property, join→link type.

**Why-ontology** — the deepest page. Decisions, not data, are the unit: every operational decision = **data + logic + action + security**. Two ideas stand out for us:
- **Decision data / decision lineage**: the ontology captures not just enterprise state but *the decisions made on top of it* — context, options evaluated, committed choice, which data version, by which app/agent. Explicitly framed as fuel to "continuously refine short-term and long-term agentic memory".
- **Scenarios**: proposed changes are staged in a sandboxed subset of the ontology to explore consequences before committing — for humans and agents alike. Agents interface with data/logic/action "through an extensible tools paradigm" — "beyond the data-centric limitations of RAG".

**Best practices** — four principles, in priority order (these are the exact principles idea.md riffs on):
1. **Domain-driven design** — model the real world, not the source data ("model reality, not systems"; name things for humans; separate identity from observation).
2. **Do not repeat yourself** (rule of three) — one canonical representation per concept.
3. **Open for extension, closed for modification** — production types are stable; extend via linked types and new interface implementations.
4. **Composition over deep hierarchies** — multiple inheritance via focused capability interfaces (Inspectable, Schedulable) instead of single-inheritance chains; workflows target interfaces, not concrete types.
Plus a pragmatism section: principles are guides; defend the invariants that are hard to fix later (naming quality, semantic clarity, security).

**Anti-patterns**: System Silos, Kitchen Sink (1:1 dataset mirroring), Department Silos, God Object, Golden Hammer, Action Sprawl, Time Machine, Misnomer.

## Relevance to the project

- This gives us a **complete candidate type system** for bacteria's memory: object types, properties, shared properties, link types, action types, functions, interfaces. We don't have to invent the meta-model — we have to *decide what subset applies* to a personal-agent memory.
- **Decision lineage is a memory-system concept**, stated by Palantir themselves: recording *why* something was concluded/decided (inputs, options, chosen action) is what turns a knowledge graph into a substrate for learning. This is arguably the missing piece in most agent memory designs and maps directly to idea.md's "conclusions-taking engine".
- **Scenarios** = a mechanism for hypothetical reasoning over the memory (what-if branches of the graph) — relates to Coyle's "no side effects until validated" ([01](01-agentic-ontologies-coyle.md)) but generalizes it: stage → simulate → review → commit.
- The four design principles double as **rules for how the memory should evolve its own schema** — e.g. an agent adding entities should obey DDD (model the user's reality, not the chat format) and the rule of three (dedupe near-identical entity types).
- "A user, or an AI agent, should be able to navigate it without friction, because the structure matches how they already think about their domain" — this is the shared-mental-model claim of idea.md, in Palantir's words.

## Connections to other sources

- Formalizes what [02](02-palantir-ontology-overview.md) pitched: triad becomes tetrad (data/logic/action/**security**) and gets a type system.
- Principle 1 ↔ DDD article (source 05); principles 3–4 ↔ ArjanCodes composition video (source 06); interfaces/polymorphism ↔ the generics/variance video (source 07) — idea.md links "the fourth principle" with covariance/contravariance; note the docs' fourth principle is *composition via interfaces*, and variance is the type-theoretic machinery behind "workflows target interfaces". To reconcile in dialogue.
- "Beyond the data-centric limitations of RAG" ↔ Coyle's neurosymbolic guardrails ([01](01-agentic-ontologies-coyle.md)): both argue plain retrieval is insufficient; the ontology adds structure the LLM can *act through*, not just read.
- Anti-pattern catalogue is a ready-made test list for semantica's model (source 09) and for our own prototypes.

## Open questions for the human

1. **Decision lineage**: do you want bacteria's memory to record decisions/conclusions as first-class objects (with links to the evidence entities and the options considered)? This looks like the natural substrate for your "conclusions-taking engine".
2. **Scenarios/branching**: is hypothetical staging (agent proposes graph changes → user reviews → commit) part of your memory UX vision? It fits the "shared mental model" flow: the agent proposes an update to the shared reality, the human ratifies it.
3. **Security dimension**: Palantir's fourth component. For a personal agent this could mean: what the agent may read/write/act on autonomously. In scope for the mental model, or out?
4. The dataset analogy (row→object, join→link) is a good teaching device for the UI. Worth adopting in bacteria's docs/onboarding?

## Provisional conclusions

- Adopt Palantir's **meta-model vocabulary** (object type / property / link type / action type / interface / function) as our working language in this repo — it's precise, documented, and maps to graph structures.
- **Decision lineage** should be promoted to a core concept of the project, on par with entities and relationships.
- The four design principles + anti-patterns become our **schema-quality checklist**, both for human modeling and for any automated (agent-driven) schema growth.
