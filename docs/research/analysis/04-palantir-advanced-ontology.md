# Analysis 04 — Deep Dive: Advanced Ontology (Landon Carter, DevCon 5)

Source: [`sources/04-palantir-advanced-ontology/`](../sources/04-palantir-advanced-ontology/raw.md)

## Summary

A Palantir ontology-team lead walks through advanced primitives, framing everything with the four design principles and the thesis: **"the ontology is effectively the software that's powering your organization"** [06:32] — so decades of software-engineering research apply directly to reality modeling.

1. **The ontology's journey** [00:48]: golden tables (data integration) → operational decision-making (actions, functions, models — the kinetics) → AI-first (LLMs layered on top, mechanizing the captured kinetics). Gotham heritage: ontologizing unstructured intel data for decades; LLMs now do that extraction well [02:15].
2. **The four principles** [02:57–06:32], stated as the crux:
   1. *Domain-driven design* — the ontology is a virtual twin **of the world, not of your datasets**; intuitive for humans *and agents*.
   2. *Don't repeat yourself (rule of three)* — explicitly justified as **context management for agents**: 12 near-identical object types make an agent (and a human) sift; one canonical type doesn't [04:22].
   3. *Open/closed* — lock core workflow nuggets; others extend with new types/workflows.
   4. *Producer-extends / consumer-super* — **covariance and contravariance**: interface-typed workflows accept any implementing object set (a workflow over `? extends Event` takes NBA games or DevCon keynotes); functions typed `? super Event` can consume subtypes [11:31]. Net effect: a **plug-and-play ontology**.
3. **Interfaces** [07:17–11:31]: interface-powered workflows run over any implementing object type; multi-inheritance (Arena implements Building *and* SchedulableResource — composition over inheritance instead of a contrived `SchedulableBuilding`); interfaces are multi-level (interfaces extend interfaces).
4. **Structs** [12:15–15:07]: multi-field properties (address = street+city+…) carrying **metadata alongside the value** (source, who/when created — provenance). LLM use case: a Slack-helper bot ontologizes the LLM's *response + relevant doc + reasoning* as struct fields for downstream processing [13:41] — capturing model reasoning as data.
5. **Reducers & struct main fields** [15:07–17:14]: properties can hold *multiple values over time* (address history); a reducer bubbles the relevant one (e.g. most recent) to the top while the history stays searchable. Main fields let a struct behave as its principal value in UIs/workflows, metadata on hover.
6. **Derived properties** [17:56–19:20]: keep data normalized; define semantic logic that infers values from linked objects (peep names = collect names over reports-to links). Avoids denormalization brittleness.
7. **Layering depth** [20:01–23:31]: row/cell/sub-cell security; **entity resolution** (Diana/Diane Mercer resolved into one identity, built from a two-layer model of entities + observations with derived properties merging them); **object-backed link types** (a link implemented by an object — VentureStaffing — that is sometimes a meaningful entity, sometimes a hidden helper you link *through*).

## Relevance to the project

- Confirms and deepens idea.md's core intuition: **reality modeling *is* software engineering**. The four principles are the bridge; we can mine PL/SE research deliberately rather than by analogy.
- Several primitives are directly memory-system-shaped:
  - **Provenance-carrying values** (structs with source/author/time metadata) — an agent memory must know where each fact came from and when. This is the micro-level counterpart of decision lineage ([03](03-palantir-ontology-docs.md)).
  - **Multi-valued properties + reducers** — memory facts change over time (people move, opinions change); keep history, surface the current value. This is a *temporal model* without a temporal database.
  - **Entity resolution** — an agent will inevitably create duplicate entities from different conversations ("Diana"/"Diane"); resolution-as-a-primitive, preserving both observations, is essential for a memory that grows bottom-up ([01](01-agentic-ontologies-coyle.md)'s bottom-up construction).
  - **Derived properties** — computed knowledge defined declaratively over the graph; a lightweight form of Coyle's inference layer ([01](01-agentic-ontologies-coyle.md)) and of "logic attached to objects" ([02](02-palantir-ontology-overview.md)).
  - **Object-backed links** — relationships that are themselves entities with properties (n-ary relations); needed the moment a relationship has a time span or metadata.
  - **Ontologizing LLM reasoning** (the Slack bot) — the agent's own outputs (answers, reasoning) become graph objects: memory of *conclusions*, not just of world facts.
- DRY justified as **agent context management** is a strong argument to reuse: a clean ontology is literally cheaper and more accurate for the LLM to navigate.

## Connections to other sources

- The four principles are the same list as the best-practices docs page ([03](03-palantir-ontology-docs.md)), with principle 4 here named *covariance/contravariance* rather than *composition over deep hierarchies* — this resolves the tension noted in analysis 03: idea.md's linking of the fourth principle to variance follows **this talk's** formulation. Both formulations are about interface-based polymorphism; variance is the type rule that makes interface-targeted workflows safe.
- Composition over inheritance ↔ source 06 (ArjanCodes); variance ↔ source 07 (Python generics talk).
- Entities + observations two-layer model ↔ "separate identity from observation" best practice ([03](03-palantir-ontology-docs.md)).
- DDD principle ↔ source 05 (DDD article).

## Open questions for the human

1. **Temporality**: do you want bacteria's memory to be historic by default (multi-valued properties with reducers) or current-state with explicit history only where needed? This decision shapes storage, UI, and the conclusion engine.
2. **Entity resolution UX**: when the agent suspects two entities are the same, should it auto-merge, propose a merge in the graph UI, or keep an "is-possibly-same-as" link? (Connects to the shared-mental-model flow: resolution is exactly a moment where human and agent must align.)
3. Are **relationships-with-properties** (object-backed links) in the core model from day one? Plain property graphs (e.g. Neo4j-style) support edge properties natively — is that enough, or do we want full "link objects"?
4. Should the agent's own **reasoning/conclusions be ontologized** as objects (Slack-bot pattern)? This seems to be your "conclusions-taking engine" substrate again, arrived at from a different direction.

## Provisional conclusions

- Add to the meta-model candidate list: **provenance on every assertion, multi-valued temporal properties, entity resolution, derived properties, reified (object-backed) relationships**.
- Treat the variance principle as: **define workflows and tools against interfaces/abstract types, never concrete entity types** — that's what keeps the ontology plug-and-play as it grows.
- The strongest cross-source pattern so far: *everything the agent does should become part of the model* (reasoning, decisions, observations) — memory is not a cache next to the loop; it's the loop's ledger.
