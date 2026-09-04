# Dialogue 06 — One memory, or two?

> Opened 2026-08-24. **The proposal is the human's**: make the graph the global concept of memory, and treat `chat_memory_entry` as a primitive earlier version of it that the richer system eventually supersedes.
>
> This is a larger decision than anything in [dialogue 05](05-what-building-it-taught.md). It changes what §1 and §5 have to specify, it would refactor a shipped and working feature in `bacteria`, and it is the first question in this project where **the model and the target codebase's own ADRs give opposite answers**.

## What made it live

Not tidiness. Three separate problems turned out to have one solution, which is usually the signal that a structure is wrong rather than merely unfashionable.

**Retrieval has no join.** ADR 0024 says the graph decides *which* confirmed memories surface, and there is no link — no foreign key, no shared identifier — between `chat_memory_entry` and any node. A graph narrows by relationship; relationships hold between entities; a key/value entry is about nothing. So the sentence in ADR 0002 has no mechanism, and **ADR 0006's kill criterion cannot even be set up**, because traversal produces assertions and the supplier must produce entries.

**Two extractors read the same transcript.** Two model calls per turn producing overlapping representations of the same sentence. "My dog is ill" can yield `pet: Canija` and `self —pet→ Canija`.

**The system knows things it may never say.** Under ADR 0024 an assertion can never be spoken. Once extraction is on, the graph holds *"Diane is Acme's CTO"* — visible in the console, contradiction-checked — and nothing can tell you, until someone activates a conclusion that happens to mention it.

## The asymmetry the proposal rests on

`chat_memory_entry` is not a different *kind* of thing from an assertion. It is a **strictly poorer** one:

| | memory entry | assertion |
|---|---|---|
| valid time | — | two bounds, three states each |
| recorded time | `created_at` only | interval; supports "what did we believe then" |
| provenance | `source`, `prompt_version` | source, trust tier, session, run |
| contradiction | impossible — one slot per key | first-class, with three states |
| evidence | — | mandatory on conclusions |
| retraction | delete | append a retraction; history survives |

It is what you build before you have a model of the world. That is the sense in which "primitive" is exactly the right word.

## The objection, and it is a real one

There is precisely one thing the two-table design has that a merged store would lose. From the agent's ADR 0017, in `chat/models.py`:

> Two tables let each primary key state its own rule, and make **"reaches the model" a question of which table a row is in** rather than of a column someone must remember to filter on.

That is a **structural** guarantee. You cannot forget a table. Replace it with `WHERE ratified` and it becomes a *discipline* guarantee — which is the exact failure mode `chat/access.py` records for ownership rules: "an ownership rule per feature, forgotten silently, with nothing in the build to notice. Ingestion has not written one."

A naive merge trades a guarantee for a convention, on the one boundary whose threat model is memory poisoning. That is not a trade worth making, and it is why the proposal needs a sharper verb than *supersede*.

## The synthesis: demote it, do not delete it

**The graph becomes the ledger. `chat_memory_entry` becomes its speakable projection.**

Not a second store — a materialized view of *what this person ratified as sayable*. Four things follow:

- **One source of truth.** Everything durable is an assertion or a conclusion, carrying time, provenance and the ability to contradict.
- **The structural guarantee survives.** Only the projection is ever injected, so "reaches the model" is still a question of which table a row is in. ADR 0017 keeps its property while stopping being a separate store.
- **[R2](03-bacteria-reconciliation.md)'s layering applies unchanged.** Ledger durable, projection rebuildable — with the ratification *decision* living in the ledger, because it is a human decision and R2's determinism test makes those durable.
- **Retrieval acquires its missing join.** Every entry would descend from a node, so "the graph narrows memory" finally has a mechanism.

That last point is the reason to believe the reframing rather than merely prefer it: the proposal and the retrieval gap have the same solution, and neither was derived from the other.

> **Superseded in one respect by the discussion of Q1 below.** This section puts the projection at the *table* boundary — `chat_memory_entry` as a view. Discussing it moved the boundary to the *protocol*: `MemoryEntry` stays as the agent's contract and the graph becomes what backs it. The reasoning is the same; the seam is one layer up, and it is a seam that already exists and already carries a version number. Left unedited because the argument for the shape stands on its own.

## What it costs

**Preferences need a representation, and this is the blocker.** `tone: concise` is not a relation between two named things, and `graph/extraction.py` explicitly refuses attributes — *"Only relationships between two named things. Not attributes ('is tired')"*. §5 has "preferences and definitions" as a first-class tier and nothing implements it. **Until the graph can hold a preference, memory must stay independent, because it is holding things nothing else can.**

**Migration is ugly and should be.** Existing entries have no graph provenance. They would be grandfathered as ratified assertions of unknown origin, which is honest and looks like what it is.

**Scope.** `chat` would stop owning memory tables — a refactor of shipped, working code, against §2's principle 5 about taking the reversible side.

**And it puts the model against the codebase.** §1 says memory *should be* an ontology. ADR 0024 says an index ranks and does not speak. Both are written down, both are load-bearing, and this proposal is the first thing that forces a choice.

## The cheap first step that tests it

**Build activation-emits** — ADR 0006 §4, already designed and unbuilt: accepting a conclusion writes an entry back-linked to it.

That produces a projection with exactly one producer, alongside the store that already works, and answers empirically whether "entry as a projection of the graph" holds up before anything is moved. If it does, the memory extractor becomes the second thing pointed at the graph. If it does not, it is a feature ADR 0006 wanted regardless.

## Questions

1. **Is the synthesis the right shape** — ledger plus speakable projection — or is the two-store split worth keeping on its own terms?
2. **Does §1 or ADR 0024 win** where they disagree? Whichever loses needs amending rather than being left to contradict the other quietly.
3. **Do preferences become assertions**, and if so what shape — a relation to a value node, an attribute on the owner, or the §5 logic tier as something the graph references rather than contains?
4. **Is activation-emits the right probe**, or does it bias the answer by building half the projection before deciding whether the projection is the design?

---

## The reframing that came out of discussing Q1

**Recorded before the answer below, because it changes what the question is.** The human's position, put directly: the keyed store was the *first* implementation of memory, the graph is a more sophisticated one that subsumes it, and the first implementation should be retired — the transcript extractor removed in favour of graph building, the memory tables dropped.

Which surfaced the thing this dialogue had been missing: **those tables are not the application's to delete.**

`bacteria.agent`'s `SessionRepository` declares eight methods and five are memory — `remember`, `forget`, `propose`, `activate`, `reject` — plus `get_state`, which returns `SessionState.memory` and `.user_memory`. `MemoryEntry` is an **agent-side type**; `assemble_context` reads it; the `remember` tool is registered by the agent. And that package carries real semver precisely because "things implement its protocols", and is meant to be vendorable into hosts that have never heard of this application.

So dropping the tables is one of two much larger things:

- **reimplement those five methods over the graph** — the application changes, the agent never notices; or
- **change the agent's protocol** — a major version bump that invalidates ADRs 0016, 0017, 0021, 0022 and 0024.

The second is a different project. The first is the human's proposal in its strongest form, and it is better than either version above:

> **`MemoryEntry` stays as the agent's contract. The graph becomes what backs it.**

`remember(key, value)` writes a ratified assertion. `get_state` projects ratified assertions into `MemoryEntry` values. `chat_memory_entry` becomes an implementation detail that can then genuinely disappear — because nothing outside the application depends on the *table*, only on the *type*.

**That moves the projection idea from the table boundary to the protocol boundary**, which is the right place for it: the boundary that already exists, that is already documented, and that already has a version number attached to it.

**Two frictions it inherits, neither of them fatal and neither yet thought about:**

- **The agent's memory is keyed and the graph is not.** `MemoryEntry` is one slot per key; `self —prefers→ concise` has no key. Projecting graph into keyed entries means deriving a key, and two preferences about different things must not collide.
- **`remember` becomes the model writing to the graph.** ADR 0016 is titled *memory is written by the owner, not the model*. If `remember` writes a ratified assertion, that title stops being true unless ratification remains a separate human act.

## Answers & agreed conclusions

**(2026-08-24) Q1 — Producer now, projection conditional; and the first question is what backs `SessionRepository`: AGREED in direction, sequencing under discussion**

**The synthesis is the right destination.** Keeping a primitive store beside a richer one that subsumes it is debt, and two extractors reading the same transcript is the smell that says so.

**What changed during the discussion is that two claims had been merged and needed separating:**

| | Claim | When |
|---|---|---|
| **Producer** | The graph becomes *a* producer of memory entries — eventually the richest | now |
| **Projection** | Every entry descends from the ledger; nothing else writes | only after the graph survives its kill criterion *and* learns preferences |

Under *producer*, an entry may exist with no ledger origin. Under *projection*, it may not. That difference is the whole of it.

**The strongest argument for two stores turns out to be neutral.** [Analysis 10](../analysis/10-agent-stack-memory.md) made the case that two irreconcilable conflict policies — overwrite-by-key versus flag-and-keep-both — justify two tables. The synthesis *keeps both*: the projection stays one-slot-per-key, the ledger stays flag-both. Two policies, two structures, one source of truth. The criterion is satisfied rather than violated.

**The argument that does bite, and it changed the recommendation.** ADR 0006 wrote the graph a kill criterion: if traversal does not beat recency on a curated graph, the fallback is vectors over confirmed entries with no edges. Memory works today with the graph *entirely disabled*, which is its default. Making a shipped feature depend on one that is explicitly on probation is backwards, and three separate things want a transitional period that strict projection does not allow — migration of entries with no provenance, the kill criterion, and preferences being unrepresentable.

**Agreed order.** Each step reversible until the last:

1. **The graph learns preferences.** Blocks everything else; see Q3.
2. **A graph-backed `SessionRepository`** — protocol unchanged, both implementations runnable side by side. This is also how the kill criterion gets settled *honestly*: one protocol, two backings, compared.
3. **Retire the transcript memory extractor**, once the graph extractor demonstrably covers what it covered.
4. **Drop the tables last**, when nothing reads them.

**The end state is step 4, and the argument is that it is the last move rather than the first.** "Remove the tables" describes the end of the work; the actual first question is *what backs `SessionRepository`*, and once that is answered the tables become a consequence rather than a decision.

**Still open in Q1**: whether the sequencing above is accepted, or whether the coupling is worth taking on now for the sake of not maintaining two systems through a long transition.

---

**(2026-08-25) Q3 — A preference is a functional relation from the owner to a value node, and the relation name is the key**

Step 1 of the agreed order blocks everything else, and this is what it needs.

**The keying friction dissolves rather than being solved.** The dialogue recorded it as a cost to think about later: `MemoryEntry` is one slot per key, `self —prefers→ concise` has no key, so projecting means deriving one and two preferences must not collide. But *one slot per key* and *one `dst` per `(src, rel)` at a time* are the same statement, and the second is what [ADR 0007](../../adr/0007-the-relation-vocabulary-is-a-catalogue.md) already calls `functional=True`.

So the relation **is** the key. `self —tone→ concise` projects to `MemoryEntry(key="tone", value="concise")`, and two preferences collide exactly when the constraint layer already says they do. Nothing new is needed to detect a contradiction between "concise" and "thorough": it is the `elena` versus `Claudia` case with a different relation.

**Why a value node and not a property on the owner.** The alternative was a `graph_property` table — key and value in columns, no node minted for "concise", which is tidier and is wrong for one structural reason: **evidence is a foreign key to `graph_assertion`.** A preference in another table could never be cited by a conclusion, never take part in a conflict, and never be superseded by the machinery that already exists. It is [A2](05-what-building-it-taught.md) again — the constraint that had no row to point at — and the answer is the same one 0007 reached: do not make a second kind of thing, make it the kind that already has a row.

The cost is real and worth naming: **`_KINDS` gains `value`, and it is the first member that is not a thing.** `person`, `organization`, `place`, `project`, `topic` are all things you could point at; `concise` is not, and [§4](../../architecture/memory-graph.md)'s promotion test — *would you point at it and call it a thing?* — says so. This is the RDF distinction between object properties and datatype properties, collapsed deliberately. Value nodes will accumulate in `graph_node` and mean something different from every other row in it.

**The tail behaves differently here, and that turns out to be the ratification mechanism.** For facts, an uncanonical relation is harmless: it sits in the log as evidence for what the catalogue should become. For preferences it is *invisible* — no catalogue entry means no key, and no key means it cannot become a `MemoryEntry`. A preference therefore reaches the model only after its relation is in the catalogue.

That is not a gap. It is the agent's ADR 0016 — *memory is written by the owner, not the model* — enforced structurally rather than by a rule anyone has to remember. **The catalogue is where a preference gets ratified**, and the `remember`-writes-to-the-graph friction the dialogue flagged is answered the same way: the model may write the assertion, and it reaches a prompt only through a relation a person put in the catalogue.

**Multi-valued preferences do not project, and should not.** "I speak Spanish and English" is not functional, so `speaks` is not a key and has no slot. The graph holds both; the projection has nothing to say. That is the correct division rather than a limitation — the projection exists to hand the model one answer.

**This gives [B4](05-what-building-it-taught.md) its field.** B4 asked whether explicit-versus-inferred should be recorded rather than implied by which table a row is in, and noted it would become a field on an assertion if this dialogue landed on ledger-plus-projection. It has. The bit is now doing concrete work — it is what separates a preference the owner stated from one the model inferred, and the projection needs it to decide what may be spoken.

**Still open, and it is the next thing**: what *ratified* is, in the row. Trust is per-slice provenance and answers a different question — which channel a claim arrived through, not whether anyone meant it. The `propose`/`activate` split in `SessionRepository` needs somewhere to land, and B4's field is the candidate. **This wants an ADR** — it would be 0008, and it is the record dialogue 06 never produced.

---

**(2026-08-25) Q1's step two is the wrong shape, found by reading the code it names**

Step two says *a graph-backed `SessionRepository`, protocol unchanged, both implementations runnable side by side* — and calls that the honest way to settle the kill criterion: one protocol, two backings, compared.

**There is no second implementation to write.** `SqlSessionRepository` is 760 lines and memory is about half of it. The rest is `create_session`, `list_sessions`, `get_state`'s transcript half, `commit`, and `extraction_progress` — sessions, conversation and a watermark. **None of that is memory and none of it moves to the graph**, which holds no transcripts and never will: [analysis 10](../analysis/10-agent-stack-memory.md)'s taxonomy puts session history and memory in different layers, and this dialogue only ever argued about the second.

A graph-backed repository would therefore be a class that delegates most of its surface to the SQL one and overrides five methods. That is not two implementations of a protocol; it is one implementation with a swappable part, described as the other thing.

**So the seam is narrower than the protocol, and better for it.** What varies is where a keyed memory *comes from* — `remember`, `forget`, `propose`, `activate`, `reject`, and the `memory` / `user_memory` / `proposals` collections in `get_state`. Everything else is identical by construction rather than by discipline.

That changes what the comparison costs. Two full repositories means keeping two things correct through a long transition, which is the objection Q1 recorded and could not price. A memory backing injected into one repository means the transition has **one** implementation of everything that is not in question, and the part that *is* in question is small enough to run both ways in the same process.

**It also sharpens the criterion.** "Does the graph beat recency" was going to be measured by swapping a large object with many differences. It is now measured by swapping the source of a keyed lookup, with everything around it held fixed — which is the difference between a comparison and an anecdote.

**Revised step two**: extract a memory port from `SqlSessionRepository`, give it two implementations — the existing tables, and the graph's `preferences_for` — and select between them by configuration. Steps three and four are unchanged, and step one is done.

---

**(2026-08-25) Q3's projection emits preferences only, and that makes retrieval a prerequisite**

The first comparison between the two stores was run against real data and reported the graph knowing nothing the tables knew. The three entries are worth reading before the conclusion:

```
has_dog    true        session   "The user explicitly stated, 'I have a dog'"
dog_name   Canija      user
user_name  Guillermo   user      (twice)
```

**None of them is a preference.** They are facts, in preference-shaped slots, because a key and a value is all the table has. And the graph already holds two of them in a better form: `user_name` is the **owner node's label** — which [ADR 0009](../../adr/0009-the-graph-is-correctable.md) decided is a rename rather than a claim, and which [07's §9](07-relation-vocabulary.md) dropped name-claims for want of a home — while `dog_name` and `has_dog` are one relation, `self —pet→ Canija`, sitting in the tail.

So the gap is not a missing catalogue entry. **A key/value entry flattens a relation into a string**, and the graph cannot emit it back as a key without inventing one. This is [the asymmetry table](#the-asymmetry-the-proposal-rests-on) made concrete: "strictly poorer" turns out to mean *poorer in a way that does not round-trip*.

**Agreed**: the projection emits preferences only — functional relations pointing at a value. Widening it to any functional relation was rejected because it would flatten a fact about an entity back into a string, undoing the thing the graph is for; growing the catalogue with `user_name` and `dog_name` was rejected because neither is a preference and the first duplicates a decision already made.

**The consequence is the part that changes the plan.** If the graph's keyed memory holds only preferences, then facts reach the model by some other route, and there is exactly one candidate: **retrieval**. So `graph_backed_memory` cannot replace the tables until step three exists — steps three and four of the order are not merely *after* retrieval, they are **blocked on** it.

That was implicit and is now stated, because the alternative reading was available and wrong: that once both stores existed the tables could be retired and retrieval added later. Doing that would have lost every fact the keyed store was holding, silently, with the comparison reporting it as the graph being *behind* rather than as the plan being incomplete.

**Revised order**: step one done, step two done, **step three (retrieval) now blocks steps three and four of retirement** rather than running beside them.

---

**(2026-08-25) Retrieval has nothing to retrieve, and the reason was predicted**

The supplier seam is built. The next piece is a graph-backed supplier — anchor resolution, bounded traversal, candidates. It cannot be written, and the reason is worth more than the code would have been.

**A supplier may return only confirmed memories.** ADR 0024 is explicit and puts it as a rule: *an index ranks; it does not speak.* Everything a model is shown must have passed through a person. So the supplier's job is to select among things already speakable, never to make something speakable by finding it.

**Under the graph, "speakable" means a `stated` assertion.** And the only claims that can reach `stated` are *preferences*, because `remember` refuses any key the catalogue has no preference relation for. So the speakable set is: functional relations, pointing at a value, hanging off the **owner node**.

Traversal from a mentioned entity cannot reach any of them. `self —tone→ concise` is not connected to `Acme` by any path that means anything — anchor resolution finds `Acme`, one hop finds `cto` and `employer`, and every one of those is `inferred` and therefore unspeakable. **A supplier written today would traverse correctly and return an empty set, every time.**

**[Dialogue 09's D3](09-the-write-routes.md) predicted this and did not know it.** It recorded that the write surface *can retract and link but cannot state*, and called a seeding route "not only a test convenience — it is the thing that would let a person say something the extractor never heard." That is the same gap, reached from the other end: nothing can promote an extracted fact into something the model may be told.

So the ordering has another link in it, and it is not the one ADR 0006 wrote:

> **A route to state a fact blocks retrieval, which blocks the kill criterion.**

0006's build order — minimum graph, review surface, retrieval — put the review surface second precisely so that retrieval would be measured on a curated graph. Curation was read as *removing what is wrong*, and retract, reject, rename and link all do that. **The half nobody built is keeping what is right**, and it turns out to be the half retrieval depends on.

**Which also makes the kill criterion measurable for the first time in a specific way.** It asks whether traversal beats recency at choosing among confirmed memories. Until a person can confirm a *fact*, the confirmed set is preferences only — perhaps half a dozen items, all attached to one node, where traversal and recency would return the same thing because there is nothing to choose between. Running it now would produce a null result and read as a verdict.

---

## Correction, 2026-08-26 — step three *is* the bet

> Recorded here rather than in [dialogue 11](11-the-name-and-the-tail.md) because it changes what the agreed order above means, and an order read on its own would be read wrongly.

The four steps treat **retire the transcript extractor** and **settle §14's bet** as separate items, the first gated on the graph "demonstrably covering what the tables covered". Looking at what the tables actually hold shows they are one item.

Seven distinct keys the transcript extractor has produced across real use, against what the graph can do with each:

| key | proposals | in the graph |
|---|---|---|
| `user_name` | 6 | `name` — **a key**, as of ADR 0012 |
| `tone` | 2 | `tone` — **a key** |
| `mother_name` | 7 | `mother` — a *claim* |
| `employer` | 5 | `employer` — a claim |
| `location` | 2 | `lives_in` — a claim |
| `acme_cto` | 2 | `cto` — a claim |
| `dog_name` | 2 | `pet` — tail, and a claim either way |

`preferences()` selects `functional and dst_kind == "value"`. `mother` is person→person, `employer` person→organization, `lives_in` person→place, `cto` organization→person. **None of them can ever be a key**, however the catalogue grows.

**So the two stores are not two implementations of one thing.** The tables turn everything into a key; the graph turns preferences into keys and everything else into claims. "Covers what it covered" is not a bar the graph can clear, because it is the wrong shape of question.

**What retiring the extractor actually does** is move five of seven observed keys from *always in the prompt* — a key, recency-ordered, up to the limit — to *in the prompt when the message is about it*, a retrieval candidate under [ADR 0011](../../adr/0011-a-confirmed-fact-may-be-spoken.md).

No knowledge is lost. What changes is **always told** to **told when relevant**, which is [§14](../../architecture/memory-graph.md)'s wager verbatim:

> If traversal-based retrieval does not beat recency once the graph has had real curation, the graph has not earned its keep.

**Step three is therefore not gated on the bet. It is the bet**, placed on five of the seven things memory holds. It cannot be taken first and measured afterwards, because taking it *is* the wager — and a wager settled by having already acted on it is not settled at all.

**What this changes in practice.** The blocker was never coverage; [Q1](11-the-name-and-the-tail.md) cleared the only key the graph genuinely lacked. It is the measurement — the instrument exists (replay both suppliers against the graph as believed *then*), and what it lacks is labels, and labels need volume.

So the unification is gated on exactly one thing, and it is the thing the whole design was built to answer.

**The sequencing above stands otherwise.** Steps one and two are done and step four is still a consequence rather than a decision. Only the reading of step three changes: it is not a migration to perform once a box is ticked, it is the moment the bet is placed.

