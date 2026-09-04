# Analysis 07 — Understanding Python generics (David Seddon, EuroPython 2023)

Source: [`sources/07-python-generics/`](../sources/07-python-generics/raw.md)

## Summary

A from-first-principles walk through variance and generics, motivated by real modeling problems at Kraken (Octopus Energy).

1. **Setup** [02:07–04:17]: `feed_animals(list[Animal])` rejects `list[Cat]` — surprising until you know why.
2. **Liskov substitution principle** [04:17]: an object may be replaced by a sub-object without breaking the program — the foundation of polymorphism (interact through the interface, not the exact type).
3. **Variance** [05:43–11:29]: a property of *composite* types — how the container's subtyping relates to its components'. Lists are **invariant** *because they are mutable* (you could add a Dog to a list of Cats); immutable tuples are **covariant** — "a good reason to prefer immutable data structures: they type-check more easily and are more flexible" [11:29].
4. **Function types** [11:29–14:59]: return types are **covariant** (a CatFinder is a valid AnimalFinder); argument types are **contravariant** (a feeder accepting `object` can stand in for one accepting `Food`; one demanding `CatFood` cannot).
5. **Custom generics** [15:41–20:03] ← the moment idea.md links: sometimes you *don't want substitutability* — the superclass exists only to share code, not for polymorphic iteration. Then don't subtype: make the class **generic over a type variable** (`Animal[FoodT]`; Cat binds `CatFood`). Generic ≠ supertype: it "floats", becoming concrete only when bound.
6. **Case study** [20:45–24:18]: Kraken's per-country customer registration. Naive subclassing (`ItalyEngine(RegistrationEngine)` overriding the argument to `ItalyContext`) is a variance violation — argument types are contravariant. Fix: `RegistrationEngine(Generic[ContextT])`; each country binds its own context. **Engines and contexts** = shared machinery, parameterized by locally-extended data.

## Relevance to the project

More abstract than the others, but it supplies the *type-theoretic laws* behind "plug-and-play ontology":

- **Substitutability is the contract of abstraction.** When bacteria's memory has capability interfaces (Schedulable, Inspectable — [04](04-palantir-advanced-ontology.md)) and workflows/tools typed against them, variance rules say exactly which substitutions are safe: things *produced* by a tool can be narrowed (covariant), things *consumed* must be widened (contravariant). Same rule Palantir states as "producer extends, consumer super."
- **Mutability breaks covariance** — a deep design signal for the memory substrate: immutable facts/observations (append-only, event-sourced — [05](05-ddd-article.md)) compose and substitute more safely than a mutable current-state store. Three sources now push toward append-only.
- **Generics without subtyping** offers a modeling option the ontology discussion hasn't had yet: some "types" in the memory shouldn't form an is-a hierarchy at all, but be *parameterized templates* (e.g. `Observation[T]`, `Conclusion[Evidence]`) — structure sharing without claiming substitutability. That's a candidate answer to when *not* to use interfaces.
- The Kraken engines/contexts pattern is a concrete architecture for **per-domain variation over shared machinery** — analogous to bacteria having one memory engine parameterized by per-context (bounded-context, [05](05-ddd-article.md)) schemas.

## Connections to other sources

- Names and proves the rule behind [04](04-palantir-advanced-ontology.md)'s fourth principle ("producer extends consumer super") — idea.md's connection is exactly right: this talk is the tutorial for that principle.
- LSP/polymorphism ↔ interfaces as capability contracts ([03](03-palantir-ontology-docs.md), [06](06-composition-inheritance.md)).
- Immutability preference ↔ event sourcing ([05](05-ddd-article.md)) and multi-valued temporal properties ([04](04-palantir-advanced-ontology.md)).
- "Superclass only for code sharing → make it generic instead" refines [06](06-composition-inheritance.md)'s "ABCs as interfaces, one layer deep": if there's no substitution intent, don't even make it an interface.

## Open questions for the human

1. How formal do you want the memory's type system to be? Options span: (a) untyped property graph, (b) typed with interfaces + informal rules, (c) typed with checked variance (tools declare what they produce/consume and the system validates substitutions like mypy does). Where on that spectrum is bacteria v1?
2. Do you see the "conclusions-taking engine" as a *consumer* typed over interfaces (contravariant — accepts anything implementing X) so it stays plug-and-play as the ontology grows?

## Provisional conclusions

- Record the law: **producers covariant, consumers contravariant, mutable containers invariant** — the safety rules for composing typed workflows over the ontology.
- Prefer **immutable observations** in the substrate; mutation happens by appending, and "current state" is derived (reducers, [04](04-palantir-advanced-ontology.md)).
- Distinguish two kinds of abstraction in the mental model: **interfaces** (substitutability intended) vs **generics/templates** (structure sharing only). Conflating them is a modeling smell.
