# 0007 — The relation vocabulary is a catalogue, not a free-text field

## Status

Proposed — 2026-08-25.

**Amends [ADR 0006](0006-the-memory-graph-is-an-assertion-log.md) rather than
superseding it.** Everything 0006 decided about the *shape of a row* stands: two
time axes, three-state bounds, three-valued overlap, conclusions as their own
table, identity linked rather than merged. What it never decided is what may go
in `rel`, and its phase one shipped with that field ungoverned.

Requires no migration. The catalogue is a literal, canonicality is computed at
read time, and no column is added or changed.

## Context

0006's phase one has been running against real conversations. It wrote **fifteen
assertions under ten distinct relation names** — a vocabulary growing almost as
fast as the data.

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

**The constraint layer has never run.** `SEEDED` is three literals — `cto`,
`ceo`, `employer` — and the intersection with the ten above is empty.
`graph_conclusion` holds zero rows and would on any amount of further testing.
This is not a temporal failure: `overlaps()` returns `True` for two open
intervals, so a constraint on `mother` would have flagged `self —mother→ elena`
against `self —mother→ Claudia` the moment the second arrived. The
conflict-and-inference machinery — the bulk of what 0006 bought — is exercised
only by its own tests, and the record's own admission that it is "more machinery
before evidence" is worse than it reads: there is no path by which this data
*could* produce evidence.

**One fact arrives under many names.** "The owner is called Guillermo" is in the
log five times, as `acquaintance`, `interlocutor` (twice), `called`, `name` and
`alternative_name`. "The owner's mother" is `parent` (three times), `mother`
(twice) and `mother_of`. Nothing collates them, so no constraint can see them as
one claim even if one existed.

**Direction is unreliable.** `self —mother_of→ Guillermo` reads as the graph's
owner being someone's mother. The owner *is* Guillermo.

### The argument was already made, and applied to one field

`extraction.py`, on `_KINDS`:

> A closed set, checked rather than trusted. An open one means the same thing
> arrives as "person", "human" and "individual" across three runs and becomes
> three node kinds — the vocabulary drift that makes a graph unusable, arriving
> one reasonable-looking answer at a time.

That is a verbatim prediction of what `rel` then did. `kind` got a checked
frozenset; `rel` got a line of prompt — *"Keep the same direction for the same
relationship every time"* — which cannot work, because there is no *every time*.
Each call is independent and the name is invented fresh. The prompt asks the
model to be consistent with runs it cannot see.

## Decision

### 0. A relation catalogue, which absorbs the constraints

A new `app/graph/catalogue.py` holds one entry per canonical relation:

```python
@dataclass(frozen=True)
class Relation:
    name: str
    sentence: str          # "<src> works for <dst>" — read to the model and to a person
    src_kind: str
    dst_kind: str
    functional: bool       # one at a time
    aliases: tuple[Alias, ...] = ()
```

`FunctionalConstraint` and `SEEDED` are folded into it. A constraint stops being
a separate object and becomes `functional=True` on an entry, which also dissolves
0006's oddity that **evidence cannot cite a constraint**: there was never a row
to point at because a constraint was never a thing, and now it is a property of a
relation rather than an entity of its own.

Stays a literal for the reason `SEEDED`'s docstring already gave, unchanged: it
moves to rows keyed by owner when an authoring route exists, since "a person has
one employer" is exactly the kind of rule a particular person is entitled to
disagree with.

### 1. Six seeded relations, admitted by what can check them

| relation | signature | what checks it |
|---|---|---|
| `employer` | person → organization | functional + asymmetric kinds |
| `cto` | organization → person | functional + asymmetric kinds |
| `ceo` | organization → person | functional + asymmetric kinds |
| `mother` | person → person | functional |
| `father` | person → person | functional |
| `lives_in` | person → place | functional + asymmetric kinds |

**The admission test is "can anything check it?"** — because §7 below attaches
constraints only to catalogue entries, so a checkable canonical relation does work
on day one and an unchecked one does nothing the tail would not do while costing a
slot in the prompt.

Two checks qualify. **Functional** produces contradictions. An **asymmetric kind
signature** catches an inverted claim — `employer (person → organization)` rejects
a flipped pair outright, while `mother (person → person)` is symmetric, catches
nothing, and earns its place on functionality alone.

The first three are inherited rather than re-earned. `cto` and `ceo` are corporate
and appeared in **zero** real rows; they stay because removing them is a separate
decision, not because a personal graph wants them.

**Frequency is deliberately not the criterion**, and the data shows why: the most
common observed relation is `parent`, which is excluded because a person has two
parents and nothing can check it, while the less common `mother` is in.

### 2. The prompt is generated from the catalogue

The vocabulary block, including each relation's reading sentence, is rendered into
`_PROMPT` rather than written beside it. Direction becomes **stated rather than
requested**: `employer` ships as *"`<src>` works for `<dst>`"*.

`PROMPT_VERSION` already derives from the prompt text, so it moves whenever the
vocabulary moves. That is the property 0006 wanted for retraction and could not
have while the vocabulary was implicit.

### 3. Canonicality is derived, never stored

A relation is canonical iff `rel ∈ catalogue`, computed at read time. **No
column.**

A stored flag would make promotion an `UPDATE` across historical rows — mutating
an append-only log, which 0006 forbids. Derived, promotion is a one-line catalogue
change, every past row reclassifies for free, and the log is never touched.

This is the same split as conclusions-versus-log and is correct rather than merely
convenient: the log records what was *claimed*; ratification is a present-tense
judgement about vocabulary, not a past-tense belief about the world, so it belongs
to the projection.

### 4. The tail is recorded, in `graph_assertion`, unmarked

A claim whose relation is outside the catalogue is written like any other.

**A tail kept outside the graph cannot be promoted without lying about time.**
Suppose `interlocutor` goes to a side table today and is ratified in October.
Inserting those claims with their original `recorded_at` asserts the system
believed them in August when it had explicitly declined to — and 0006's own
"recorded time cannot be backfilled" forbids it. Inserting them with today's
timestamp loses when the claim was made. In the graph neither arises.

It is also the same table by the criterion already in use: two stores are
justified by **two irreconcilable conflict policies**, and a non-canonical claim
has the same policy as a canonical one — flag and keep both.

The tail being *visible* is the point. It is the evidence for what the catalogue
should become, and it is how anyone learns that `interlocutor` is junk.

### 5. Aliases canonicalize, and carry a converse flag

`called`, `name`, `alternative_name` → one relation. Extraction rewrites an
aliased relation before the assertion is built, and the model's original word
stays in `attrs`.

Collapsing is safe here in a way node merging is not. 0006 established that
splitting one person across two nodes is recoverable and collapsing two people
into one is not; **for relations the asymmetry inverts**, because the original
word survives in the log and a wrong alias is undone by re-reading it. Merging is
the cheap direction.

`mother_of` is not a synonym of `mother` but its **converse**, so an alias carries
a flag that swaps `src` and `dst` when applied. That is what turns
`self —mother_of→ Guillermo` into a correct edge rather than merging a backwards
one.

### 6. A kind signature is enforced for canonical relations

A canonical claim whose ends have the wrong kinds is flipped if flipping satisfies
the signature, and dropped otherwise. Non-canonical claims are not checked — there
is no signature to check them against.

**This catches some inversions and not all**, and saying so is the point:
`employer (person → organization)` catches a flip immediately; `mother (person →
person)` catches nothing. For the symmetric cases the reading sentence in §2 is
the prevention and human review is the backstop. There is no cheap total fix, and
claiming one would repeat the mistake of trusting the prompt line.

### 7. Constraints run only on canonical relations

`SEEDED`'s docstring worries that a wrongly-inferred constraint "generates false
contradictions *forever*". Restricting evaluation to ratified relations is what
bounds that: the layer that must not produce false contradictions never sees a
name nobody approved.

### 8. Promotion is a batch chore, and reports rather than acts

A periodic chore counts non-canonical relations — a `GROUP BY rel` over the log,
which is why §4 matters operationally as well as temporally — and logs those
seen three or more times.

Not built:
    Anything that acts on the count. Promotion is a change to the literal in §0
    until an authoring route exists, and inventing one here would commit to a
    review surface before the one 0006 already owes has been built. The rule of
    three decides *when to ask*, and the asking is still a person reading a log
    line.

### 9. A name is a property, not a relation

The extractor stops emitting name-claims. `self —name→ Guillermo` makes
"Guillermo" a node, and it did: node `a8127237` labelled `Guillermo`, kind
`person`, sits beside node `783e1dc6` labelled `self` — **the same human as two
person nodes**, with no `same_as` to join them. Five of fifteen rows are one
name-claim wearing six hats.

The prompt already forbids attributes and the model ignored it five times, so the
rule moves from the prompt into the validator: a claim whose `dst` is a bare
personal name for the `src` is not a relationship.

Not built:
    Where a name-claim goes instead. "The owner is called Guillermo" should
    **rename the `self` node** — the missing half of 0006's reserved owner node,
    whose id is derived precisely *because* its label stays correctable, and
    nothing corrects it. That route is a write path and this record does not open
    one. Until it exists the claim is dropped and counted, which loses a real fact
    and is the recoverable direction.

## Consequences

**No migration, and that is the argument for doing it now.** 0006 was expensive to
defer because it was schema. This is a literal, a validator and a derived
predicate; it costs the same today and in six months. What it does not cost today
is six months of rows under a vocabulary nobody governed.

**Aliasing makes an existing defect visible and worse.** Three name-claims under
three relations become three *identical* edges once canonicalized, and `observe()`
does not compare against `current()` — `_assertion_id` hashes the run's `now`, so
idempotence covers a retried job and never a repeated claim. The duplicate-row
problem is independent of this record and gets uglier the moment this lands.

**The retraction key churns.** `PROMPT_VERSION` deriving from the catalogue is
what §2 wants, and it means every catalogue edit starts a new version — so "retract
everything from one bad fortnight" gets more precise and "compare claims across
versions" gets harder. Only the first was ever asked for.

**The graph knowingly contains unratified rows.** `GET /graph` gains a tier: some
edges use approved vocabulary and some do not. The console already carries `trust`,
`status`, `ends` and `reason`, so this is one more dimension of an existing kind
rather than a new kind — but "what is in my graph" now has a two-part answer.

**Junk accumulates permanently**, because 0006 left retention open and nothing here
closes it. `interlocutor` will sit in the log forever. This is the retention hole
rather than a tail problem — canonical rows accumulate identically — and a side
table would not have fixed it, only moved one slice of it somewhere with no viewer.

**Ranking is left undecided.** Whether a non-canonical relation may influence
retrieval is a phase-three question and is named here so it is not settled by
accident. Nothing leaks to a prompt either way: 0006's two surfaces mean an
assertion never contributes text, so the worst a junk relation can do is affect
ordering.

**Three defects found in the same pass are untouched** and each needs its own
record or fix: duplicate rows on re-mention; `session_id` and `run_id` null on
every row though both columns exist and are indexed; `valid_from` null on every row
because the model answered `tense: current` fifteen times out of fifteen, which
leaves succession inference with no boundary to work from.

### The one to dislike

This makes the extractor's output narrower before there is any evidence the graph
helps, which is the same bet 0006 made and lost ground on. If the kill criterion
goes against the graph, a governed vocabulary was ceremony on top of ceremony.

The honest defence is only that it is cheap and reversible: deleting
`catalogue.py` and the validator returns the system to exactly where it is today,
with the tail rows still in the log and still readable, because §3 and §4 never
wrote the decision into the data.

## Alternatives rejected

**A closed enum for `rel`, mirroring `_KINDS`.** The obvious symmetry, and wrong
twice. `kind` is five members describing what *sorts* of thing exist; `rel` is the
long tail of a personal life, and there is no number at which the enum is finished,
so every unanticipated relation is a silent drop. And the drops are the least
affordable part: those five name-claims are the strongest available evidence that
the owner's name needs a canonical relation. **A closed enum discards exactly the
information needed to decide what the enum should contain.**

**Per-claim human ratification.** Matches the growth doctrine's letter and fails on
prerequisites and cost. The review surface does not exist — `GET /graph` is
read-only and the write routes are unbuilt — so ratification means building that
first. And it is a blocking gate on every novel relation, which in the first month
is most of them; curation belongs in batch.

**Adopt schema.org's property vocabulary.** Roughly 1,400 properties, which is not
a seed but a 1,400-member closed enum — worse than ten rather than better. It
cannot fit in a prompt, and if it could the model would nearest-match instead of
proposing honestly, so everything becomes `knows`: clean-looking and empty.
Borrowing only its *names* for the six was considered and dropped — camelCase,
web-markup-shaped, several reading badly for a personal graph — since the
load-bearing properties are small, top-down and checkable, and the naming source is
not one of them.

**Seed the catalogue from the observed rows.** Looks like the bottom-up choice and
is not. It is an anecdote rather than a sample — one person, two days, mostly
deliberate testing — and it is circular, because `interlocutor`, `acquaintance` and
`mother_of` exist *precisely* because nothing governed the predicate. Building the
catalogue from them canonicalizes the noise it exists to prevent. The cold-start
argument also forbids it outright: a vocabulary has to exist *before* there is
data.

**Keep the tail outside the graph.** Cleaner console, and it makes promotion
impossible without either backfilling recorded time or discarding when the claim was
made. Also a second store for rows with an identical conflict policy.

**Add more constraints to `SEEDED` and leave `rel` free.** The cheapest thing that
makes `graph_conclusion` non-empty, and it treats the symptom. The next ten
conversations produce ten more relation names, and the constraint list chases a
vocabulary that grows faster than it does.
