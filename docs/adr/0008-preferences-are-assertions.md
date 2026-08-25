# 0008 — Preferences are assertions, and the relation is the key

## Status

Proposed — 2026-08-25.

Unblocks step one of a four-step order worked out in the same research repo that produced 0006 and 0007: **the graph learns preferences**, which blocks everything after it.

**Does not retire `chat_memory_entry`.** That is steps three and four of the same order and each is its own decision. This record makes the graph *able* to hold a preference; nothing here changes what backs `SessionRepository`, and both stores keep running.

Requires a migration — two columns on `graph_assertion`. That is a real cost and [ADR 0007](0007-the-relation-vocabulary-is-a-catalogue.md)'s "no migration, so do it now" argument does not transfer.

## Context

The application has two memories. `chat_memory_entry` is one slot per key, overwritten, proposed and confirmed by a person. `graph_assertion` is an append-only bi-temporal log that flags contradictions and keeps both sides. [ADR 0006](0006-the-memory-graph-is-an-assertion-log.md) built the second beside the first and named no relationship between them.

Two extractors now read the same transcript and produce overlapping representations of the same sentence, and ADR 0024's retrieval — the graph deciding which memories surface — has no join to make, because a key/value entry is about nothing and a graph narrows by relationship.

The proposal that came out of discussing it is that **`MemoryEntry` stays as the agent's contract and the graph becomes what backs it**. That is a protocol boundary rather than a table boundary, which matters: `bacteria.agent` carries real semver because things implement its protocols, and five of `SessionRepository`'s eight methods are memory. Dropping tables is an application change; changing `MemoryEntry` is a major version bump that invalidates ADRs 0016, 0017, 0021, 0022 and 0024.

Getting there needs one thing first, and it is the only thing this record decides: **the graph cannot currently hold a preference at all.**

### The two frictions this has to answer

**The agent's memory is keyed and the graph is not.** `MemoryEntry` is one slot per key. `self —prefers→ concise` has no key, and two preferences about different things must not collide.

**`remember` would become the model writing to the graph.** The agent's ADR 0016 is titled *memory is written by the owner, not the model*. If a tool call writes a speakable preference, that title stops being true.

## Decision

### 1. A preference is an assertion, not a new kind of row

Same table, same two time axes, same conflict policy.

**The criterion already in use says so.** Two stores are justified by two irreconcilable conflict policies: memory overwrites by key because a model must not be handed two current answers, and assertions flag and keep both because a contradictory world has to be representable. A preference does not need a third policy — it needs *both*, at different layers. The ledger keeps both and flags them; the projection hands out one. That is one source of truth with two structures over it, which is what §7 builds.

### 2. The relation is the key, and the friction dissolves

`self —tone→ concise` projects to `MemoryEntry(key="tone", value="concise")`.

**"One slot per key" and "one `dst` per `(src, rel)` at a time" are the same statement**, and ADR 0007 already calls the second `functional=True`. Nothing has to derive a key, nothing has to prevent collisions, and a contradiction between *concise* and *thorough* is detected by machinery that has been running since 0006 — it is the same shape as two claims about one person's mother, with a different relation.

A preference relation is therefore an ordinary catalogue entry that happens to point at a value:

```python
Relation(
    name="tone",
    invariant="A person prefers one tone at a time.",
    sentence="<src> prefers <dst> answers",
    src_kind="person",
    dst_kind="value",
    functional=True,
)
```

### 3. `value` joins `_KINDS`, and it is not a thing

The object of a preference is a node whose label *is* the value. `concise`, `spanish`, `europe/madrid`.

**This is the concession, and pretending otherwise would be dishonest.** `person`, `organization`, `place`, `project` and `topic` are all things a person could point at. `concise` is not, and the design's promotion test — *would you point at it and call it a thing?* — says it should not be an object. This is RDF's split between object properties and datatype properties, collapsed on purpose, and value nodes will accumulate in `graph_node` meaning something different from every other row there.

The alternative is §11.

### 4. `origin` records whether anyone meant it

A new column, two values: `stated` when the owner said it, `inferred` when something worked it out.

**`trust` does not answer this and was never asked to.** It records which channel a claim arrived through — a defence against attacker-controlled text reordering what a person approved — and after the first turn essentially every transcript slice contains an assistant message, so the tier is nearly always `third-party` whoever was speaking. *Which channel* and *did anyone mean it* are different questions, and the second is the one a projection has to answer before speaking.

This is the field that design pass asked for, and it stops being a distinction implied by which table a row is in.

### 5. Ratification appends; it does not flip a flag

`activate` writes a **new assertion** with the same triple and `origin="stated"`. The proposal stays exactly where it was.

Nothing mutates, which is the whole grain of the log — 0006 permits `recorded_until` to change and nothing else, and a mutable `status` column would make an append-only design append-only by convention. It is also the more honest reading: **ratification is not a property of a claim, it is the owner making the claim.** What the model proposed and what the owner said are two events and the log records events.

`reject` and `forget` close belief by setting `recorded_until`, which is the field that already changes.

**`_unrepeated` must key on `origin`.** It currently suppresses a claim the log already believes, keyed on the triple and its valid interval, and would otherwise swallow every activation as a restatement. `trust` is deliberately *not* in that key — a claim arriving through a different channel is news about the channel rather than about the world — and `origin` is the opposite case: the owner confirming what the model guessed is exactly news about the world.

### 6. `scope` says where a preference applies, and `session_id` says where it came from

A second column, `user` or `session`, defaulting to `user`.

These are different questions and the existing column answers only one. `session_id` is provenance: a claim learned in one conversation may well apply everywhere. A session-scoped preference is one that applies only within the conversation it was recorded in, which is what the agent's ADR 0021 already distinguishes, so the pair `(scope, session_id)` reproduces it without inventing a third concept.

### 7. The projection is mechanical

`get_state` becomes: for every functional preference relation in the catalogue, the currently-believed assertion with `origin="stated"` and a scope that admits this session, rendered as `MemoryEntry(key=relation.name, value=node.label)`.

No ranking, no model call, no choice. If two `stated` assertions are believed for one relation the constraint layer has already flagged it, and the projection takes the most recently recorded — because a projection must return one answer and the alternative is returning none, which is worse for a caller that only wanted to know the tone.

### 8. The catalogue is where a preference is ratified

**The tail behaves differently for preferences than for facts, and that is load-bearing rather than a gap.**

For a fact, a relation outside the catalogue is harmless: it sits in the log as evidence for what the catalogue should become. For a preference it is *invisible* — no entry means no key means nothing to project — so a preference reaches a model only once a person has put its relation in the catalogue.

That answers the second friction. The model may call `remember` and write an assertion; it cannot make one speakable, because the vocabulary it would have to be spoken under is a literal in the source. **ADR 0016's title survives structurally**, enforced by the shape of the system rather than by a rule someone has to keep in mind.

### 9. Multi-valued preferences do not project, and should not

"I speak Spanish and English" is not functional, so `speaks` is not a key and has no slot. The graph holds both claims; the projection has nothing to say about them.

This is the right division rather than a limitation. The projection exists to hand a model one answer, and a relation that admits several has no answer to hand.

## Consequences

**A migration, and the cheap-now argument does not apply.** Two columns with defaults, no table, no backfill of meaning — every existing row is `origin="inferred"`, `scope="user"`, which is what it always was. But 0007 could be argued for on being free and this cannot.

**`graph_node` becomes two kinds of table.** Entities and values share it, `refer_to` matches both by normalized label, and a query for "every person in my graph" now has to exclude a kind. Nothing enforces that a value node is only ever a `dst`.

**Nothing is retired.** Both memories keep running and two extractors keep reading the same transcript. This makes the graph *capable* of backing `SessionRepository`; it does not make it do so, and the duplication stays until steps two through four.

**The kill criterion gets closer to answerable.** Step two — one protocol, two backings, compared — is what settles honestly whether the graph beats recency, and it cannot be built until preferences are representable. ADR 0006's §9 has been unanswerable for this reason and not only for the missing retrieval.

**`origin` will be wrong sometimes and cheaply.** An extractor marking a genuine user statement as `inferred` costs a proposal that needed confirming; the reverse would speak something nobody said. The default is `inferred` and extraction never writes `stated`, so the expensive direction requires an explicit act.

### The one to dislike

**A value node is a category error the system will now contain by design**, and the defence is only that the alternative is worse. Everything else in `graph_node` is a thing with an identity that persists across mentions; `concise` is a word. Two preferences pointing at the same value node will look like a relationship between them and will not be one.

The honest version is that the design's meta-model has *properties* and the implementation has only *links*, and rather than build the property layer this record spends a node kind to avoid it. If value nodes turn out to poison identity — and `refer_to` matching them by label is where that would start — the way out is §11, and it is a migration rather than a revert.

## Alternatives rejected

**A `graph_property` table**, key and value in columns, no node minted. Tidier, and wrong for one structural reason: **evidence is a foreign key to `graph_assertion`.** A preference living elsewhere could never be cited by a conclusion, never take part in a conflict, and never be superseded by machinery that already exists — the same defect 0006 left behind with constraints, which had no row to point at, and which 0007 fixed by refusing to make a second kind of thing. Doing it again here would be repeating a mistake already paid for once.

**A mutable `status` column** — proposed, active, rejected — mirroring `graph_conclusion`. Rejected because a conclusion is explicitly *not* the log: it is a derived belief and may be re-derived, where an assertion is a record of what was claimed. A status that flips would make an activation indistinguishable from the proposal having always been stated, which loses exactly what the two time axes exist to keep.

**Keying preferences by a derived string** rather than by the relation — hashing the value, or asking a model for a key. Both invent an identifier that nothing else in the system uses, and both make collision a runtime accident rather than a modelled constraint. The relation is already a key and already has the uniqueness rule attached.

**Reusing `trust` as ratification.** It is per-slice provenance, it is nearly always `third-party` after the first turn, and overloading it would make one column answer two questions that disagree — the failure mode 0007 fixed in `sentence`, repeated in a place with worse consequences.

## Not built

**What proposes a preference.** Extraction produces facts and no relation in the catalogue points at a value yet. Seeding a few and teaching the extractor to notice them is the obvious next step and is deliberately not here: this record is the shape, and the shape should be settled before anything starts writing to it.

**Retention.** Unchanged and still the largest hole. A preference is exactly the kind of thing whose staleness matters most, and nothing here gives it an expiry.
