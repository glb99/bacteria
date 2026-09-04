# Dialogue 14 — The domain with no package

> Opened 2026-08-30 by the human, while reading how the architecture agent composes a runtime:
>
> *"isn't it an inconsistency to call the runtime from conversation.py in the case of the architecture domain, but from a services.py in the 'chat' domain? Even I think that chat domain isn't a real domain, could be our 'personal' domain implementation."*

The first half is a naming question and the smaller of the two. The second half is an ontology question about the codebase that models ontologies, and it is the one worth the dialogue: **`chat` is a surface that has been standing in for a domain, and the domain it stands in for has never had a name.**

[Dialogue 13](13-the-subject-changed.md) predicted this without seeing it. It recorded that the personal assistant was *"the way of validating the most basic substrate"*, and that two domains are what force the seam to be found. What it did not say is that the first domain, having been built *as* the proof, never got separated from the thing it was proving.

## The measurement

Architecture was the second domain, and it was given a package. Comparing the two is the evidence.

**Nine of the substrate's ten relations are personal-domain policy.** `graph/catalogue.py` declares:

| | |
|---|---|
| `employer`, `cto`, `ceo`, `mother`, `father`, `lives_in`, `tone`, `language`, `name` | policy — a personal life |
| `same_as` | substrate — identity, domain-neutral |

`architecture/catalogue.py` borrows only `Relation` from that module and declares its own four words locally, with the reason stated in its docstring: *"the meta-model is borrowed, the entries are not… the substrate travels, the policy does not."* That is [dialogue 10 Q4](10-a-place-to-stand.md)'s split, honoured by the second domain and not by the first.

**The substrate imports the surface, at load time.**

```
chat         -> graph          11 edges
graph        -> chat            2 edges   <- a cycle
architecture -> graph           6 edges
graph        -> architecture    0 edges   <- acyclic
```

The two edges are `graph/extraction.py:52 -> chat.models` (module-level) and `graph/tasks.py:67 -> chat.service` (deferred). The second domain has a clean one-way dependency on the substrate. The first is entangled with it in both directions.

**And the personal domain's adapter is inside the surface package.** `chat/` holds roughly 1,700 lines that are not about chatting — `extraction.py`, `memory.py`, `review.py`, `graph_candidates.py`, `graph_memory.py` — alongside `models.py`, `views.py` and `repository.py`, which are.

So the personal domain exists, is substantial, and is distributed across two packages named for neither it nor each other.

## Why it looks fine from inside

Nothing is broken. Every test passes, the boundaries hold, and no reader of `chat/` is confused about what the code does.

This is the same shape as the defect `architecture/catalogue.py` was written to fix, stated in its own opening: the ontology **smeared into its adapter**, undetected because *"a single module writes every one of them — exactly the condition that held for `rel` right up until it stopped holding."*

Here the condition is *there is one personal domain and one chat surface*, so the two can share a package without anyone noticing which parts belong to which. It stops holding the moment a second surface wants the same domain — a voice interface, an API, an import from another assistant — or a second domain wants the same surface.

## Questions

### Q1 — Is `chat` a domain, or a surface with a domain inside it?

The claim on the table: **`chat` names a transport, not a slice of reality.** The domain is a person's life; the ontology over it is the ten relations minus `same_as`; the instance is one user's graph. `chat` is how claims arrive, the way `derive.py` is how architecture's claims arrive — and nobody would call `derive` a domain.

If that is accepted, the honest structure is `personal/` beside `architecture/`, holding the vocabulary now in `graph/catalogue.py` and the adapter now in `chat/`; `chat/` keeps the session, the messages, the routes; `graph/` keeps the log, the temporal machinery, identity, and the meta-model.

**What would make this wrong:** that a personal ontology is genuinely open-ended in a way architecture is not, so its vocabulary belongs with the machinery that governs vocabulary growth — the tail, the promotion rule, the ratification queue all live in `graph/catalogue.py` and exist *for* this domain. Moving the entries out and leaving the growth doctrine behind might separate two things that only work together.

### Q2 — Does the refactor happen, and what triggers it?

It changes no behaviour. It is a large edit to working code, justified entirely by a claim about what the code *means* — which is the kind of justification this project exists to take seriously and also the kind that produces churn.

Three positions, and the human's choice is the answer:

1. **Do it now**, while there are two domains and the seam is visible. The cost only grows.
2. **Do it when a third domain arrives** (business, research). Two instances found the seam; three would prove which parts are substrate — and a refactor performed against two examples risks encoding the second one's accidents.
3. **Never do it; write down that the packages are misnamed and what that costs.** [Dialogue 12 Q1](12-nothing-ever-leaves.md)'s move, and the cheapest honest option: a paragraph now against an argument later.

**The counterweight, recorded because it weakens position 1.** The architecture package is four days old. Treating it as the reference shape means generalising from the newer, smaller, less-exercised of the two — and its own catalogue admits it is closed only because *"there is nothing to discover"* in its domain, which is precisely not true of a personal life.

### Q3 — Is "compose the runtime for one turn" a named thing?

The smaller half of the question, and it should not be answered by picking a filename.

`chat/service.py` and `architecture/conversation.py` do the same job — decide the provider, register the tools, choose the gate, run one turn — and share no name, no signature, and no type. `service` is one of the five **roles** the classifier proposes for this codebase precisely because it recurs without meaning anything; `conversation` names what the module is.

But the real question is whether this is a *role* both domains fill, or two unrelated compositions that happen to rhyme. If it is a role, it wants a shared shape — the way `SuppliesMemoryCandidates` is a protocol in `agent/` with an implementation in `app/chat/`. If it is not, the names should simply stop pretending, and `chat/service.py` becomes `chat/conversation.py`.

The evidence available: the two differ in gate (`OnlyReads` vs allow-all), in statefulness (one session per ask vs a persistent session), and in tool ownership. That is three differences on four responsibilities, which argues for two compositions rather than one role — but it was never asked, and one of the two was written by copying the other's shape.


---

## What is agreed

### Q1 — `chat` is a transport, and it dissolves

**Agreed 2026-08-30.** The human's ruling:

> *"a transport, so could we remove it and move the artifacts inside the real domains? also we could extract some shared concepts if exists to core/"*

So `chat` is not renamed, kept, or reduced — it goes, and each of its parts moves to whatever already has a claim on it.

**The counter in the question above is answered rather than dodged.** The worry was that the personal vocabulary belongs beside the machinery that governs vocabulary growth. It does not: `architecture/catalogue.py` already borrows `Relation` and declares its own entries, and the tail, the promotion rule and the ratification queue are *machinery* that stays in `graph/`. Entries move; the doctrine does not. The second domain had already demonstrated the split before the question was asked.

**`core/` takes none of it, and this is decided by a check rather than by taste.** The human proposed it as a destination for shared concepts. Two of this codebase's own boundaries refuse it:

> *"Features own their tables, tasks, and routes. `core/` holds nothing that names a domain concept."*

`_core_declares_a_table` fires on any table declared under `core/`, and a session is a domain concept. Moving anything there would cross two of the four decidable boundaries, and the console would report it the same afternoon.

The genuinely shared things already have homes, and neither is `core/`:

- protocol shapes → `agent/` (`SessionRepository`, `SuppliesMemoryCandidates`)
- domain-neutral substrate → `graph/` (log, temporal, identity, `Relation`, `same_as`)

`core/` is infrastructure — db, settings, jobs, observability. **A thing that looks shared and fits neither `agent/` nor `graph/` is evidence it is not shared yet**, which is the rule that also settles Q4.

**Where the parts go:**

| | |
|---|---|
| `extraction`, `graph_memory`, `graph_candidates`, `review`, `comparison` | `personal/` |
| the nine relations in `graph/catalogue.py` | `personal/catalogue.py` |
| `models`, `views`, `access` — the surface | `personal/`, see below |
| `repository.py` and the four memory tables | `personal/`, see [Q4](#q4--sessions-is-not-a-package-and-per-domain-implementation-is-already-the-pattern) |
| `build_model_client` | `agent/` — a provider factory, not a domain concern |

**The personal domain holds its own surface**, because `architecture/` does. Splitting `personal` from its views would make it the only domain that does not own the way its claims arrive, and the asymmetry this dialogue opened about would survive the refactor in a new spelling.

**No table is renamed.** Classes move, every `__tablename__` stays. A pure import-graph refactor needs no migration; renaming needs one plus a data move, and would bury a meaning change under mechanical risk.

### Q2 — Now

**Agreed 2026-08-30.** Position 1, against the recorded counterweight.

The argument that decided it is stronger than *the cost only grows*: **a second domain is already reaching into the first for something that was never personal.** `architecture/views.py` imports `chat.service.build_model_client` — one edge, and it is infrastructure wearing a domain's package name. The cycle is not the only symptom, and a third domain would inherit both.

**Sequenced so each step stands alone:**

1. **Break the cycle first**, as its own commit — `graph/extraction.py:52 -> chat.models` is module-level and is the edge that makes `graph` not-substrate.
2. Create `personal/`; move the five adapter modules and the surface.
3. Move the nine relations out of `graph/catalogue.py`.

**The acceptance test is measurable by this codebase's own tool**: `graph -> personal` must be **0 edges**, matching `graph -> architecture` today. Anything left in `graph/` that only `personal/` imports was never substrate.

### Q3 — Partly answered, and the rest stays open

`build_model_client` moves to `agent/` regardless: it is generic, and it sits in `chat/service.py` only because the first agent was composed there.

Whether *compose the runtime for one turn* is a **role** both domains fill remains open. The evidence still argues against — three differences on four responsibilities — and nothing about the refactor forces the answer. Recorded so that it is not settled silently by whichever filename survives.

### Q4 — `sessions/` is not a package, and per-domain implementation is already the pattern

**Raised and answered 2026-08-30 by the human**, against a shared `sessions/` package proposed during the discussion:

> *"is it ok being a separate folder besides the real domains? Wouldn't each domain be in charge of implementing the agent protocol?"*

It would not be ok, and the proposal was wrong for a reason stated one exchange earlier and then not applied: **building a shared home for a thing with one user.**

**Per-domain implementation is what already happens.** Two implementations of one structural `Protocol`:

| | | |
|---|---|---|
| `agent/session/protocol.py` | `SessionRepository` | the seam, shared |
| `agent/session/store.py` | `SessionStore` | in-memory reference — what architecture chose |
| `app/chat/repository.py` | `SqlSessionRepository` | durable — what personal wrote |

Architecture did not pick the in-memory one by preference. That surface **refused** persistence outright: *"a caller deciding what a model was told is exactly the property this system spends most of its design protecting."* So this is one durable implementation with one user, not a duplicated concern.

**And `sessions/` fails the five-part test the second domain established** — no adapter, no vocabulary, no rules, no proposer, no surface. Tables and a repository and no domain. A package beside the real domains that is nobody's domain is precisely what `chat/` became, which is how `build_model_client` ended up there. Creating it would re-create the diagnosed defect under a tidier name.

**The cost of the ruling, recorded because it is real.** `personal/` then owns four tables whose columns name nothing personal — `MemoryContent` is `value`, `reason`, `created_at`, and its own docstring says *"whatever owns it."* That is a wart. It is the smaller one, and this codebase's boundary check would not flag it: features own their tables.

**The trigger, named narrowly so it cannot be invoked vaguely:** a *second* domain wanting durable sessions. Architecture has one plausible route to it — capturing **why** a boundary was accepted, which is thrown away today, and which is the reason that quietly lapsed [dialogue 13](13-the-subject-changed.md) closed on. If that gets built the move is cheap: the protocol exists, and the tables already have no domain in their columns.

---

## Closing note

Q1 and Q4 were decided by running this codebase's own checks against a proposal about this codebase, which has not happened before. `core/` was refused as a destination because `_core_declares_a_table` would have reported it, and the acceptance test for the whole refactor is an edge count `derive.py` produces.

That is [§14](../../architecture/memory-graph.md)'s bet arriving from an unplanned direction. The negotiation surface was built to let a human argue with an agent about a codebase; here it settled an argument about **its own** arrangement, and the deciding evidence in both answers was a number rather than a preference — nine of ten relations, two edges against zero, one import of a provider factory.

The pattern [dialogue 13](13-the-subject-changed.md) named holds a seventh time: the repository was the more reliable witness. What this dialogue adds is that it is now a witness that can be *cross-examined* — *is `chat` a domain* has an answer with a query behind it, and *did the refactor work* will have the same query behind it.

Related: [dialogue 10 Q4](10-a-place-to-stand.md) (substrate vs policy), [dialogue 11](11-the-name-and-the-tail.md) (the catalogue and its tail), [dialogue 13](13-the-subject-changed.md) (two domains force the seam), [§3](../../architecture/memory-graph.md) and [§10](../../architecture/memory-graph.md).
