# Dialogue 07 — Nobody governs the predicate

> Opened 2026-08-25, from testing the shipped extractor rather than from reasoning. Fifteen assertions written by real conversations, and **ten distinct relation names among them** — a vocabulary growing almost as fast as the data.
>
> Sibling to [dialogue 05](05-what-building-it-taught.md): another thing implementation found that no amount of thinking had. Independent of [dialogue 06](06-one-memory-or-two.md) — the predicate needs governing whether there turn out to be one store or two.

## What the rows show

```
 rel              | count        rel              | count
------------------+-------      ------------------+-------
 parent           |     3        alternative_name |     1
 interlocutor     |     2        called           |     1
 mother           |     2        mother_of        |     1
 owns             |     2        name             |     1
 acquaintance     |     1        pet              |     1
```

Three consequences, in order of severity.

**The constraint layer has never run.** `SEEDED` is three literals — `cto`, `ceo`, `employer` — and the intersection with the ten above is empty. `graph_conclusion` holds zero rows and would on any amount of further testing. This is not a temporal failure: `overlaps()` returns `True` for two open intervals, so a constraint on `mother` would have flagged `self —mother→ elena` against `self —mother→ Claudia` the moment the second arrived. The whole conflict-and-inference layer, which is the part the model is *about*, is exercised only by its own tests.

**One fact arrives under many names.** "The graph owner is called Guillermo" is in the log five times, as `acquaintance`, `interlocutor` (twice), `called`, `name` and `alternative_name`. "The owner's mother" is `parent` (three times), `mother` (twice) and `mother_of`. Even seeding `mother` leaves `parent` and `mother_of` outside it.

**Direction is unreliable.** `self —mother_of→ Guillermo` reads as the graph's owner being someone's mother. The owner *is* Guillermo.

## The prediction was already written down

`extraction.py`, on `_KINDS`:

> A closed set, checked rather than trusted. An open one means the same thing arrives as "person", "human" and "individual" across three runs and becomes three node kinds — the vocabulary drift that makes a graph unusable, arriving one reasonable-looking answer at a time.

That is a verbatim description of what `rel` then did. **The same argument was made and applied to one of the two vocabularies.** `kind` got a checked frozenset; `rel` got a line of prompt — *"Keep the same direction for the same relationship every time"* — which cannot work, because there is no *every time*: each call is independent and the name is invented fresh. The prompt asks the model to be consistent with runs it cannot see.

## Why the obvious fix is wrong

Do to `rel` what was done to `kind`: a closed enum, checked, non-conforming claims dropped. It fails twice.

`kind` is five members describing what *sorts* of thing exist. `rel` is the long tail of a personal life — `pet`, `owns`, `lives_in`, `allergic_to`, `landlord`, `GP` — and there is no number at which that enum is finished. Every unanticipated relation becomes a silent drop.

And the drops are the part least affordable. Those five rows for one fact are not noise; they are the strongest available evidence that *the owner's name* needs a canonical relation. **A closed enum discards exactly the information needed to decide what the enum should contain.**

It also contradicts [§10](../../architecture/memory-graph.md), which is explicit that schema grows bottom-up in evidence and is ratified top-down. An enum is top-down authorship — the thing §10 says a person will never sit down and do.

## Why per-claim confirmation is also wrong

Novel relations land pending; the human ratifies. It matches §10's letter and fails on prerequisites and cost.

**The surface does not exist.** `GET /graph` is read-only, the write routes are unbuilt, and [B5](05-what-building-it-taught.md) already records that there is no route by which anything leaves the graph. Ratification means building that first.

**It is a blocking gate on every novel relation**, which in the first month is most of them. §10's own answer is that curation happens in batch, as an agent chore — not as a prompt per claim.

## The shape: canonical core, open tail, rule of three

Neither of the above, and closer to what §10 already describes.

1. **A relation catalogue.** One entry per canonical relation: name, reading sentence, `src` kind, `dst` kind, functional or not, aliases. Seeded small — the six-types argument applied to edges.
2. **The prompt is generated from it**, shipping the catalogue as the *preferred* vocabulary with reading sentences (`employer`: src works for dst), so direction is **stated rather than requested**. `PROMPT_VERSION` derives from the prompt text, so it moves when the vocabulary moves — which is exactly the retraction key [B3](05-what-building-it-taught.md) wants.
3. **The tail is written, not dropped.** A relation outside the core is recorded and marked non-canonical. The tail is the evidence for what the core should become.
4. **Constraints attach only to canonical relations.** `SEEDED`'s own docstring worries a wrongly-inferred constraint "generates false contradictions *forever*"; restricting constraints to ratified names is what bounds that. It also dissolves [A2](05-what-building-it-taught.md): a functional constraint stops being a separate object with no row to point at and becomes a flag on a catalogue entry.
5. **Promotion is a batch chore.** A non-canonical relation seen three times is proposed for the core — §10's rule of three, run as the ontology-refactoring chore it already describes.

## Aliasing, and the asymmetry running the other way

The core carries synonyms: `called`, `name`, `alternative_name` → `name`.

Collapsing is safe here in a way node merging is not. [A5](05-what-building-it-taught.md) established that splitting one person across two nodes is recoverable and collapsing two people into one is not. **For relations the asymmetry inverts**: the model's original word stays in `attrs`, so a wrong alias is undone by re-reading the log. Merging is the cheap direction.

One wrinkle, and it is the direction bug: `mother_of` is not a synonym of `mother`, it is the **converse**. An alias entry therefore needs a converse flag — alias to `mother`, swap the ends — and that is what turns `self —mother_of→ Guillermo` into a correct edge rather than merging a backwards one.

**The honest limit.** A kind signature catches some flips and not all: `employer (person → organization)` catches an inverted pair immediately; `mother (person → person)` is symmetric in kinds and catches nothing. For those the reading sentence is the prevention and human review is the backstop. There is no cheap total fix, and claiming otherwise would be the same mistake as trusting the prompt line.

## Where it lives

`SEEDED`'s docstring already answered, and the answer transfers unchanged: a literal until an authoring route exists, moving to rows keyed by owner when it does — since "a person has one employer" is exactly the kind of rule a particular person is entitled to disagree with. It starts as a literal in code.

## What this does not fix

Four defects found in the same pass, each needing its own decision, none touched by the catalogue:

- **A re-mention writes a new row.** `self —parent→ mom` exists three times, all believed. `_assertion_id` hashes the run's `now` deliberately, so idempotence covers a retried job and never a repeated claim; `observe()` never compares against `current()`. The projection returns N copies of one edge.
- **`session_id` and `run_id` are null on every row.** Both columns exist and are indexed; `_claim()` never sets them though `session_id` is in scope. No claim can be traced to its conversation, and "retract everything from one bad run" has no run to filter on.
- **`valid_from` is null on every row and `valid_to` is `OPEN_ENDED` on every row.** The model answered `tense: current` fifteen times out of fifteen. No fact has a start, so succession inference can never find the boundary it needs.
- **`mom` is a node.** A role, not a name; it will never match `Claudia` or `elena` by normalized label, so one person is three nodes. A5 calls that the recoverable direction — but `same_as` appears nowhere in the package, so nothing can ever collapse them.

## Questions

### Q1 — Does the tail live in the graph?

Writing non-canonical claims rather than dropping them is step 3, and it has a real cost: the graph knowingly contains rows nobody ratified, `GET /graph` gets messier, and "what is in my graph" acquires two tiers of answer.

The alternative keeps the graph clean and logs rejected claims somewhere that is not the graph — at the price of a second place to look, which is the structure [dialogue 06](06-one-memory-or-two.md) is currently arguing *against* in a different guise.

**Question**: tail in the graph and marked, or tail outside it and clean? — **answered below, in the graph.**

### Q2 — How small is the seed?

§10 says about six object types. The equivalent number for relations is not obvious, and the two failure modes are asymmetric: too small and everything is tail, too large and it is the closed enum with extra steps.

The ten observed names collapse to roughly four ideas — *name*, *parent*, *pet/owns*, *acquaintance*. That is one person over two days.

**Question**: seed from the observed data, or seed from schema.org's vocabulary as §10 does for types? — **answered below: neither, six chosen by checkability.**

---

## Answers & agreed conclusions

### Q1 — The tail lives in the graph, and canonicality is derived rather than stored

**Agreed 2026-08-25.** A claim whose relation is outside the catalogue is recorded in `graph_assertion` like any other. Whether its relation is canonical is computed at read time as `rel ∈ catalogue`, and is never a column.

**What decided it: a tail outside the graph cannot be promoted without lying about time.** Suppose `interlocutor` is written to a side table today and ratified in October. Moving those claims into the graph offers two options and both are wrong. Insert them with their original `recorded_at` and the log now asserts the system believed them in August, when it had explicitly declined to — a replay of an August run would show memory that was never there, which is the exact falsification bi-temporality exists to prevent, and [§2](../../architecture/memory-graph.md)'s rule that **recorded time cannot be backfilled** forbids it outright. Insert them with today's `recorded_at` and the history of when the claim was actually made is gone.

In the graph the problem does not arise. Belief was recorded correctly and once; promotion changes only how the predicate is classified, never what was believed or when.

**The already-agreed criterion rules the same way.** [Analysis 10](../analysis/10-agent-stack-memory.md) gave the test for when two stores are justified — *two irreconcilable conflict policies*. A non-canonical claim has the same policy as a canonical one, flag and keep both. Same policy, same table. A `graph_rejected_claim` beside `graph_assertion` would reproduce at small scale the structure [dialogue 06](06-one-memory-or-two.md) is arguing to dissolve at large.

**The cost, which is real and is not a tail problem.** Junk accumulates permanently, because [B5](05-what-building-it-taught.md) is right that nothing ever leaves the graph. But canonical rows accumulate identically: this is the retention hole, and a side table does not fix it — it relocates one slice of it somewhere with no viewer, which is where garbage goes *unnoticed* rather than where it goes away. The visible tail is partly the point; seeing `interlocutor` listed is how anyone learns it is junk.

The "messy console" objection is smaller than it looked. The view already carries `trust`, `status`, `ends` and `reason`; one more dimension is not a new kind of complexity.

**Why derived and not stored.** A `canonical` column makes promotion an `UPDATE` across historical rows — mutating an append-only log, which the design forbids. Computed at read time, promotion is a one-line catalogue change, every past row reclassifies for free, and the log is never touched.

That is not merely convenient, it is the correct modelling, and it is the same split as conclusions-versus-log: **the log records what was claimed; canonicality is a projection over it.** Ratification is a present-tense judgement about vocabulary, not a past-tense belief about the world, so it belongs to the projection rather than to the row.

**Deferred deliberately (Q1)**: whether a non-canonical relation may influence retrieval ranking. Constraints already will not touch it (step 4); ranking probably should not either, but retrieval does not exist, so the question is phase 3 and is recorded here so it is not decided by accident. Nothing leaks to a prompt either way — [§8](../../architecture/memory-graph.md)'s two surfaces mean an assertion never contributes text, so the worst a junk relation can do is affect ordering.

### Q2 — Six relations, chosen because something can check them

**Agreed 2026-08-25.** The seed is neither derived from the observed rows nor borrowed wholesale from an external vocabulary. It is small, authored top-down before the data, and admits a relation on one test: **can anything check it?**

| relation | signature | what checks it |
|---|---|---|
| `employer` | person → organization | functional + asymmetric kinds |
| `cto` | organization → person | functional + asymmetric kinds |
| `ceo` | organization → person | functional + asymmetric kinds |
| `mother` | person → person | functional |
| `father` | person → person | functional |
| `lives_in` | person → place | functional + asymmetric kinds |

Two kinds of check qualify. **Functional** — "one at a time" — produces contradictions. An **asymmetric kind signature** catches an inverted claim: `employer (person → organization)` rejects a flipped pair outright, while `mother (person → person)` is symmetric and catches nothing, earning its place on functionality alone.

Names are ours, in the `lower_snake_case` the prompt already asks for. The first three are inherited from `SEEDED` rather than re-earned; `cto` and `ceo` are corporate and appeared in **zero** real rows, and they stay only because removing them is a separate decision. `mother` and `father` are the additions that pay immediately — `mother` is exactly the constraint that would have flagged `elena` against `Claudia`.

Everything else starts as tail: `owns`, `pet`, `parent`, `knows`, `works_on`. Unratified rather than rejected, and promoted by the rule of three once it recurs.

**Why not the observed data.** It looks like the §10-compliant choice and is not. It is an anecdote rather than a sample — one person, two days, mostly deliberate testing. It is circular: `interlocutor`, `acquaintance` and `mother_of` exist *because* nothing governed the predicate, so building the catalogue from them canonicalises the noise the catalogue exists to prevent. And §10 seeds top-down for a reason that forbids it — *"an empty graph is a bad cold start: with no vocabulary the agent invents inconsistently from day one"* is an argument for a vocabulary existing **before** there is data, which means it cannot be derived from data. §10's shape is seed top-down, grow bottom-up; the rule of three already does the second half.

**The proof that frequency is the wrong criterion** is in the rows themselves. The most common observed relation is `parent`, three occurrences, and it is deliberately excluded: a person has two parents, so nothing can check it. The less common `mother`, two occurrences, is in.

**Why not an external vocabulary either.** schema.org has roughly 1,400 properties, so adopting it is not a seed decision but a 1,400-member closed enum — worse than ten rather than better. A large menu degrades extraction: it cannot fit in a prompt, and if it could the model would nearest-match instead of proposing honestly. **The tail's value is that a novel proposal is legible** — `interlocutor` is visibly junk, `pet` is visibly right. Forced to choose from a large menu everything becomes `knows`, which looks clean and says nothing.

Borrowing schema.org's *names* for the few relations we do pick was considered — Coyle's advice not to reinvent taxonomies — and **dropped**. Its names are camelCase and web-markup-shaped, several read badly for a personal graph (`alumniOf`, `homeLocation`), and the benefit is a tiebreaker against bikeshedding unless interop is wanted later. The load-bearing properties are *small*, *top-down* and *checkable*; the naming source is not one of them.

**Why err small.** The failure modes are asymmetric in the same shape as [A5](05-what-building-it-taught.md). Too small and the catalogue does little on day one, the rule of three fills it, and constraints arrive late — recoverable. Too large and the model nearest-matches into it, the tail stops carrying signal, and the graph **looks clean while quietly mislabelling** — which is not recoverable, because nothing shows you the mistake.

### Q3 — A name is not a relation, and this is a third of the bad rows

**Raised while answering Q2, and separate from the catalogue.** Applying the checkability test to `name` breaks it usefully: `self —name→ Guillermo` makes "Guillermo" a **node**.

It is in the database now. Node `a8127237` labelled `Guillermo`, kind `person`, sitting beside node `783e1dc6` labelled `self` — the same human as two person nodes, with no `same_as` to join them.

A name is a property, not a thing. The prompt already forbids attributes — *"Only relationships between two named things. Not attributes"* — and the model violated it five times out of fifteen: `acquaintance`, `interlocutor` (twice), `called`, `name` and `alternative_name` are one name-claim wearing six hats.

So "the owner is called Guillermo" should **rename the `self` node**, not draw an edge. That is the missing half of [A6](05-what-building-it-taught.md): the owner node's id is reserved *because* its label stays correctable, and nothing corrects it. Fixing it deletes a third of the bad rows and is independent of the catalogue.

**Question**: does the rename route get built alongside the catalogue, or does the extractor merely stop emitting name-claims until there is somewhere for them to go?

**Answered by building it**: the extractor stops, and the fact is dropped. The rename is a write path and ADR 0007 opened none, so a name-claim is discarded and counted. That loses something real, in the recoverable direction.

---

## What building it taught

> ADR 0007 shipped 2026-08-25, five commits behind one PR. Four things the record got wrong or did not reach, none of which were visible from reasoning.

### C1 — A rule's *reading* and a rule's *arguability* are two artifacts

The record's `Relation` sketch had one `sentence` field described as "read to the model and to a person". It cannot be both. *"`<dst>` is the CTO of `<src>`"* tells a model which way round to write a claim and **states no rule**; *"An organization has one CTO at a time"* is the thing a person is invited to disagree with.

An existing route test caught it, which is the interesting part: the console asserts the sentence shown beside a contradiction, and that assertion was already encoding the distinction the new dataclass had collapsed. `MENTAL-MODEL.md` §5 says a constraint is a contestable hypothesis; **contestability turns out to be a field, not a property of the wording.**

### C2 — Two decisions in one record contradicted each other

§5 gave `called`, `name`, `alternative_name` → one relation as the aliasing example. §9 of the same record decided those are not relationships at all. So the example aliased three names to an entry §9 had already forbidden from existing, and nothing in reading the record made that visible — both sections are individually right.

Worth generalizing: a record long enough to need cross-references is long enough for two of them to disagree, and the compiler for that is an implementation.

### C3 — The name rule had to become a denylist, and that is a real loss

§9's rule is *"a claim whose `dst` is a bare personal name for the `src` is not a relationship"*. Implementing it requires knowing that "Guillermo" is a name and "Acme" is not, which nothing available can do without asking a model a question it would answer confidently and wrongly.

So it ships as a list of naming predicates — the shape this whole dialogue argued against for `rel`. The defence is only that the failure is cheap: a missed spelling costs one junk node in the tail, where the general version would cost a wrong answer with nothing showing it. **The tail is what makes an admittedly-incomplete check tolerable**, which is a second argument for Q1 that Q1 did not make.

### C4 — A converse alias must be recognized and never offered

Not in the record at all. Rendering the catalogue into the prompt naïvely produced:

```
mother - <src>'s mother is <dst> (also: mother_of)
```

which advertises the inversion the converse flag exists to undo. Converse aliases are now excluded from the prompt: they catch a word the model reaches for unasked, and listing one as an alternative spelling invites the exact error. **An alias table is read in two directions and only one of them should be public.**

### C5 — "Periodic chore" met a codebase with no scheduler

§8 specified a periodic chore. `core/jobs.py` lists scheduled jobs under "not built" and says they belong in the worker entrypoint. Building one for a report would have been infrastructure the record did not ask for — and a scheduled job writes its list into a log nobody tails, where the record's own *Not built* note already said the asking is a person reading a line.

It shipped as `bacteria-admin relations`. **A report with no actor is a command, not a job**, and specifying a cadence for something nothing acts on was the record over-reaching.

### C6 — The evidence was destroyed by running the tests

`just test-app` truncates `graph_assertion`, and `compose.yml` points development and tests at one database. The fifteen rows this dialogue and [08](08-the-schema-is-ahead-of-the-writer.md) were built from are gone.

Nothing analytical was lost — the counts and examples are quoted here and in the ADR, which is what the "raw before analysis" rule is for. But it sharpens 08's note into something this repo's method depends on: **live rows are evidence, and they are the one kind of evidence held somewhere that was never designed to keep it.** Anything a dialogue rests on belongs quoted in the dialogue, not cited by reference to a table.

### Verified

The claim the record rests on, checked against the live stack rather than the tests:

```
recorded: 2
CONFLICT rule=mother state=conflict
```

Two current `mother` claims for one person, reported as *provable* rather than *possible*. Before the catalogue the seeded relations and the extracted ones had an empty intersection, so `graph_conclusion` could not have become non-empty by any amount of use.
