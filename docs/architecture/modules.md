# The module map

Which Python module represents what, and — the part that actually confuses
people — which of the three things called "the ontology" each one is.

[`README.md`](README.md) beside this file is the shape of the whole in the order
a request moves through it. This one is a dictionary: open it when you know the
concept and want the file, or have the file and want to know what layer it is
standing in. What each module *does* stays in its docstring; this says where it
sits.

Scoped to the three packages that make up the memory graph and the two
ontologies over it. `auth/`, `core/`, `ingestion/`, `evaluation/` and
`entrypoints/` are described by their own package docstrings and by
[`README.md`](README.md); nothing here changes what they own.

---

## "The ontology" is three things

Almost every misunderstanding about this codebase is one of these three being
mistaken for another.

| Level | The question it answers | Lives in | Per domain? |
|---|---|---|---|
| **Meta-model** | What *is* a relation? What may a vocabulary say about itself? | `graph/catalogue.py` | no — one, shared |
| **Vocabulary** | Which relations does *this* domain use? | `personal/catalogue.py`, `architecture/catalogue.py` | **yes** — one each |
| **Contents** | What is claimed, by whom, and when was it believed? | rows in `graph_assertion` | one table, partitioned |

`graph/catalogue.py` states its own half of the split in its first line — *"The
shape a vocabulary has, and nothing any particular one says."* It defines
`Relation`, `Alias`, `Vocabulary`, `Resolution` and `PROMOTION_THRESHOLD`, and
declares exactly one relation name: `same_as`, which is identity and therefore
substrate rather than policy.

`architecture/catalogue.py` states the other half: *"the meta-model is borrowed,
the entries are not."*

That sentence is load-bearing and was arrived at the hard way. Nine of the
substrate's ten relation entries — `employer`, `cto`, `ceo`, `mother`, `father`,
`lives_in`, `tone`, `language`, `name` — sat in `graph/catalogue.py` until the
second domain made the mistake visible. Nothing was broken; every test passed.
The defect was only that the substrate could not travel, and nobody could see it
while there was one domain. `docs/research/dialogues/14-the-domain-with-no-package.md`
has the measurement and the argument.

### Vocabulary is not contents

A catalogue entry is not a claim. `mother` existing as a relation says nothing
about who anyone's mother is.

And **canonicality is derived, never stored**: whether a relation is in the
catalogue is computed at read time (`repository.vocabulary.is_canonical`), so
promoting one out of the unratified tail changes what a row *means* without
touching the row. A `canonical` column would have made promotion a migration
over history, which is the one thing an append-only log must never need.

### Where a partition comes from

Every read is narrowed by `SqlGraphRepository._mine()`, and the docstring there
says why it is a property of the repository rather than an argument at each call
site: *"a property of the repository cannot be forgotten at a call site."*

| Domain | `ontology` value | Meaning |
|---|---|---|
| personal | `NULL` | one graph per user, no further split |
| architecture | `architecture:<project_id>` | one partition **per project**, prefixed so a row is legible to somebody reading the database by hand |

The vocabulary rides on the repository for the same reason. Worth knowing while
reading that code: `architecture/views.py` constructs `SqlGraphRepository` with
an `ontology` but **no** `vocabulary`, so it gets `EMPTY`. The three service
functions that consult one (`lookup`, `is_canonical`, `names`) are reached
through `observe()`, and architecture writes through `record()` instead — so
this is latent rather than wrong today, and would stop being latent the moment
architecture routed a write through the service layer.

---

## `graph/` — the substrate

Domain-neutral by rule, and the rule is checkable: **`graph` must import no
domain.** It is 0 edges to `personal` and 0 to `architecture` today, and that
number is the acceptance test the split was held to. Anything in here that only
one domain imports was never substrate.

| Module | Owns |
|---|---|
| `catalogue.py` | the meta-model — `Relation`, `Alias`, `Vocabulary`, `Resolution`, the rule of three, `same_as` |
| `log.py` | `Assertion` and the verbs over it: `state_at`, `current`, `retract`, `log_expire`, `supersede` |
| `temporal.py` | `Interval`, and `overlaps()` returning `True` / `False` / **`None`** |
| `identity.py` | `Node`, `normalize()`, `owner_node_id()` — which thing a label refers to |
| `constraints.py` | `Conflict`, and the four states: none, conflict, possible, explained |
| `conclusions.py` | `Conclusion`, `stale_after()` — beliefs drawn rather than told |
| `inference.py` | `infer_succession()` — filling in a boundary a constraint implies, without recording it as observed |
| `models.py` | the tables |
| `repository.py` | rows ↔ values, partitioned by `ontology` |
| `service.py` | the sanctioned write door — `observe`, `revise`, `link` |

Two of these are the temporal core and are easy to skim past. `temporal.overlaps`
is three-valued on purpose: two claims that both run to an unknown end **may**
overlap, and answering `False` there would silently delete a conflict.
`inference.py` exists because the opposite shortcut was tried in a prototype —
writing an inferred boundary onto the successor made the intervals provably
apart, the conflict vanished, and the assumption became invisible exactly when
it began to matter.

---

## The two domains

Both are laid out against the same five roles. The table is the fastest way to
see what a third domain would have to bring.

| Role | `personal/` | `architecture/` |
|---|---|---|
| **Vocabulary** | `catalogue.py` | `catalogue.py` |
| **Adapter** — turns a source into typed claims | `claim_extraction.py`, `memory_extraction.py`, `dates.py` | `derive.py` (the `ast` parse), `layout.py` (finding the source), `probes.py` (asking the world) |
| **Rules** | inside `catalogue.py`, as `functional` and `invariant` on each entry | `checks.py` — a separate module, and a literal |
| **Proposer / reviewer** | `graph_candidates.py`, `review.py` | `classify.py`, `decisions.py` |
| **Surface** | `views.py`, `graph_views.py` | `views.py`, `conversation.py` |

And what each has that the other does not:

| | |
|---|---|
| `personal/memory.py` | the memory port — a keyed memory behind an interface, so it can come from elsewhere ([ADR 0010](../adr/0010-memory-has-a-port.md)) |
| `personal/graph_memory.py` | that port, backed by the assertion graph instead of by two tables |
| `personal/comparison.py` | asks both stores the same question and reports where they differ — the migration's evidence |
| `personal/models.py`, `repository.py`, `access.py`, `service.py`, `tasks.py` | hosting the agent: session tables, the durable `SessionRepository`, ownership, composing a turn, the background jobs |
| `architecture/tools.py` | what a model may **ask** about a codebase, and nothing it may do to one |
| `architecture/models.py`, `repository.py`, `service.py` | the project list, and `model_of()` — the only part of the feature that touches a filesystem |

**The adapter is what a domain is.** That is the sentence the whole arrangement
turns on, from `docs/research/dialogues/13-the-subject-changed.md`: the
generator differs entirely per domain; the log, the surface, the actions and the
negotiation are built once; the rules differ in content and are identical in
shape. A candidate that shares subjects, adapter and truth condition with an
existing ontology is not a new one.

### Derived and stated, in the same table

The two domains invert each other, and the `origin` column is where that lands.

|  | personal | architecture |
|---|---|---|
| Who proposes | a language model reading a transcript | a deterministic `ast` parse |
| Default `origin` | `inferred` | `inferred` for the parse, `stated` for a judgment |
| Trust model | **auto-commits**; the owner retracts what is wrong | **nothing is accepted** until a person judges it |
| Ground truth | none — *which Diane?* | derivable, exact — a module is its path |

`derive.py` reads what nobody chose. `checks.py` and `decisions.py` hold what a
person said. `checks.py` puts it plainly: *"A derived fact is not contestable; a
boundary is a claim somebody made and may later be wrong about."*

---

## Where the map is honest about being wrong

Two things in the arrangement above are known to be in the wrong place. Both are
recorded here rather than only in a dialogue, because a map that hides its own
defects is how the last one went unnoticed for months.

**Boundaries are source code and should be rows.** A functional constraint is a
property of a *relation* and belongs in the catalogue, which is where it is. A
boundary is a *proposition over the graph* — it has an author, a date, and can be
wrong — so it belongs in the log as an assertion with `origin="stated"`, which is
where it is not. `checks.py` names its own destination: *"rows keyed by scope,
with a date stated and a date retired, so that retiring a boundary is an event
rather than a deletion from a file."*

What blocks the move is not storage. `Boundary.sentence` is already data, kept
verbatim so it can be disagreed with; `Boundary.decides` is a Python callable,
and the model's own rule is that rules are *"stored as data, not code — arbitrary
code would need a runtime and a sandbox."* Note that **four of the seven
boundaries have `decides=None`** and could be rows today, and that
`decisions.py` already writes classifications to the log with `origin="stated"`
and `closed_by="superseded"`. The machinery exists one level down and was never
carried up.

**`personal/` owns four tables whose columns name nothing personal.**
`MemoryContent` is `value`, `reason`, `created_at`, and its own docstring says
*"whatever owns it."* This is a wart, knowingly taken: a shared `sessions/`
package was proposed and refused, because a package beside the real domains that
is nobody's domain is precisely what `chat/` became. The trigger for revisiting
it is named narrowly — **a second domain wanting durable sessions** — so that it
cannot be invoked on taste.

---

## Where the reasoning is

| | |
|---|---|
| The conceptual model | [`memory-graph.md`](memory-graph.md) |
| The substrate / policy split | `docs/research/dialogues/10-a-place-to-stand.md`, Q4 |
| The catalogue and its unratified tail | `docs/research/dialogues/11-the-name-and-the-tail.md`, [ADR 0007](../adr/0007-the-relation-vocabulary-is-a-catalogue.md) |
| *The adapter is what a domain is* | `docs/research/dialogues/13-the-subject-changed.md` |
| Why `chat/` dissolved, and the 0-edge test | `docs/research/dialogues/14-the-domain-with-no-package.md` |
| What earns its own ontology | `docs/research/dialogues/15-the-third-axis.md`, Q5 |
