# Analysis 01 — Why Agentic Systems Need Ontologies (Frank Coyle)

Source: [`sources/01-agentic-ontologies-coyle/`](../sources/01-agentic-ontologies-coyle/raw.md)

## Summary

Coyle argues that agents (probabilistic, LLM-based) and ontologies (formal, symbolic) are two lineages now converging into **neurosymbolic AI**, and that the ontology's job is to keep the LLM inside guardrails.

Key points, in talk order:

1. **Two lineages** [02:10–04:18]: agents come from early AI (McCarthy, Minsky — perceive → decide → act); ontologies go back to Aristotle's categories of being, formalized by Quine and **Gruber (1993)**: *"a formal specification of a shared conceptualization"* — which is exactly what we want to hand to agents: our conceptualization of a domain.
2. **What an ontology is** [05:02–05:45]: not complicated — entities with properties, and relationships between entities. Graph databases arose because relational schemas were too rigid; a graph lets you attach a new entity/property/relationship without restructuring.
3. **Building one** [06:29–08:36]: top-down (domain experts enumerate entities/relations — the 1980s expert-systems approach, which failed to scale) vs bottom-up (harvest entities/relations from actual activity, e.g. customer interactions, and grow the graph). Reuse existing taxonomies: schema.org, FOAF, Dublin Core, DBpedia.
4. **Inference/constraint layer** [09:19–11:31]: RDFS and OWL sit *beside* the graph and let you derive new facts and enforce constraints — domain/range ("teaches" implies teacher/student), transitive properties (ancestor), functional properties ("hasFather" is unique → two names for the father must be the same individual).
5. **The agentic loop** [12:12–16:32]: loops make agents Turing-complete but they can break, drift, and burn tokens. His integration proposal: in the classic tool-use loop (LLM proposes tool call → runtime executes → result returned), insert a **validator step after the tool runs** — the validator is a reasoner operating over the domain ontology that judges whether the result is reasonable; if not, loop back to the LLM or bring a human in.
6. **Layered validation** [17:13–18:40]: *"Pydantic at the door, ontology at the ledger"* — type-check parameters at the boundary, semantically check results against the ontology. Agents should have **no side effects** until the ontology validation passes.
7. **Concrete catches** [18:40–20:08]: a second refund on the same order (functional property), a payout sent to a support rep instead of the buyer (disjoint classes), an invented status value like "probably shipped" (enumerated range). Things that are "funky" to catch in free text are trivial for a symbolic checker.

## Relevance to the project

- Gives us the **canonical definition** to anchor GLOSSARY: ontology = formal specification of a shared conceptualization. Note how close "shared conceptualization" is to idea.md's "shared mental model between human and agent" — the definitions almost coincide.
- Positions the memory-as-ontology not just as *storage* but as an **active guardrail component in the agentic loop** — the memory system can validate agent actions, not only inform them. This is a concrete mechanism for idea.md's "conclusions-taking engine could work on this substrate".
- The **bottom-up construction** path maps directly to how an agent's memory actually grows: entities/relations harvested from conversations and actions, incrementally attached to the graph — with optional top-down schema from the user.
- The **side-layer idea** (RDFS/OWL-like rules sitting beside the graph) suggests bacteria's memory could have two strata: the entity/relationship graph, plus a rules/constraints layer that enables inference and validation. The idea.md notion of "hierarchies, clusters… more metadata for modeling reality" may live in this same side layer.

## Connections to other sources

- Gruber's "shared conceptualization" ↔ Palantir's ontology-as-shared-operational-model (sources 02, 03) — to verify once ingested.
- Top-down expert modeling ↔ DDD's collaborative domain modeling with ubiquitous language (source 05).
- Constraint/validation layer ↔ Palantir's "logic sources" and action validation (source 02).
- Semantica (source 09) presumably implements exactly this graph+reasoning stack — check whether it has an OWL-like layer.

## Open questions for the human

1. Should bacteria's memory validate/veto agent actions (Coyle's guardrail role), or only inform them (pure context/recall role)? This is an architectural fork: memory as *police* vs memory as *map*.
2. Do we want a formal constraint language (RDFS/OWL-like, machine-checkable) in v1, or start with a plain property graph and add the rules layer later?
3. Bottom-up growth (agent harvests entities from interactions) vs top-down (user defines the schema first) — which is the primary flow for bacteria? Both?

## Provisional conclusions

- The memory substrate should be a **property graph** (entities + typed relationships + properties), not tables — cheap to extend, matches the visualization goal.
- Plan for a **separate rules/inference layer** beside the graph, even if v1 doesn't implement it: it's what turns the memory from a picture into a guardrail.
- The neurosymbolic loop gives a precise seam for integration: **after tool execution, before commit** (no side effects until validated).
