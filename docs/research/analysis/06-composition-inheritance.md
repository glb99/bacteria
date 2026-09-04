# Analysis 06 — Composition Is Better Than Inheritance (ArjanCodes)

Source: [`sources/06-composition-inheritance/`](../sources/06-composition-inheritance/raw.md)

## Summary

A worked refactoring showing why "favor composition over inheritance" (the Gang-of-Four maxim) holds.

1. **The setup** [01:26]: three employee classes (Hourly, Salaried, Freelancer) each mixing personnel data, commission logic, and pay computation → duplication + too many responsibilities.
2. **Inheritance attempt** [03:30–09:11]: a base `Employee` class helps a little, but separating commission via subclasses (`SalariedEmployeeWithCommission`, `FreelancerWithCommission`…) fails: duplication remains, and every new dimension (bonus?) causes a **combinatorial explosion of subclasses**. Inheritance is also "the strongest possible coupling in OOP" — each subclass depends on superclass internals [09:53].
3. **Composition** [09:53–17:47]: identify the independent *concepts* — employee identity, payment contract, commission — give each its own (small) class hierarchy, and compose: `Employee` **has a** `Contract` and optionally **has a** `Commission`; `compute_pay` just combines their `get_payment()` results. Any contract × commission combination now works without new classes.
4. **Made generic** [18:30]: `Contract` and `Commission` both become abstract interfaces; the employee depends only on those. "Is-a" replaced by "has-a" everywhere except at interface boundaries.
5. **The distilled doctrine** [21:24–22:47]: use inheritance almost exclusively for **abstract base classes = interfaces** (one layer deep, like most GoF patterns); the ABC *reduces* coupling (depend on the interface, not an instance), while concrete inheritance *adds* coupling. Composition + interfaces = decoupled code. (Mentions Pydantic for validated data classes — same tool Coyle names in [01](01-agentic-ontologies-coyle.md).)

## Relevance to the project

This source is about *how to model*, and it transfers to ontology design almost 1:1 (which is exactly why Palantir cites the principle):

- **Combinatorial explosion argument** = Palantir's `SchedulableBuilding` anti-pattern ([04](04-palantir-advanced-ontology.md)): entity types must not multiply per capability combination. In the memory graph: don't create "WorkFriend", "OldColleagueWhoIsAlsoNeighbor" types — compose a Person with capability facets/interfaces.
- **"Has-a" over "is-a"** is a rule for the agent's schema growth: when bacteria needs to attach a new aspect to an entity, prefer a *linked* object or facet (composition) over specializing the entity's type (inheritance). This is the open/closed principle in graph form: core entity types stay closed; extension happens by attaching.
- **Interfaces one-layer-deep** matches Palantir's capability interfaces (Inspectable, Schedulable) and grounds idea.md's link between open/closed and composition: open/closed is *achieved by* composition against interfaces.
- The `Contract`/`Commission` decomposition is a miniature ontology-refactoring case study — useful as a prototype scenario later: could an agent perform this decomposition on a "Kitchen Sink" entity automatically, guided by the rule of three?

## Connections to other sources

- Direct elaboration of principles 3–4 in [03](03-palantir-ontology-docs.md)/[04](04-palantir-advanced-ontology.md); the Arena example there is this video's employee example in ontology clothing.
- "Depend on the interface, not the instance" is the coupling-side statement of the variance principle in [04](04-palantir-advanced-ontology.md) and of source 07's generics.
- Small single-responsibility classes echo DDD's value objects / focused entities ([05](05-ddd-article.md)).

## Open questions for the human

1. In bacteria's ontology, how should "capabilities" attach to entities — as **interfaces the entity type implements** (Palantir-style), as **linked facet objects** (pure composition), or both? (They differ in UI: a facet is a visible node; an interface is type metadata.)
2. Should schema *specialization* (subtyping) be allowed at all in v1, or restricted to interfaces + composition to keep the graph flat and pluggable?

## Provisional conclusions

- Modeling rule for the memory system: **compose, don't specialize** — entity types stay small and stable; new aspects arrive as attached objects or implemented interfaces.
- The anti-pattern to guard against in agent-driven schema growth is precisely the subclass explosion: an LLM asked to "create a type for X" will happily mint `XWithY` types; the ontology layer must channel that into composition instead.
