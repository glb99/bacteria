# Dialogue 11 — The name, and what the tail cannot say

> Opened 2026-08-26, from running `bacteria-admin memory-diff` over three real conversations rather than from reasoning. [Dialogue 06](06-one-memory-or-two.md) agreed a four-step order to unify the two stores; steps one and two are built and **have never been switched on**, and step three — retiring the transcript extractor — is blocked by exactly two things.
>
> Both are questions rather than defects, and one of them reverses a decision already recorded.

## What the comparison said

```
9807a99f   tables: 2   graph: 0     has_dog · user_name
44340afd   tables: 1   graph: 1     tone only in graph · user_name only in tables
b5d2d5d1   tables: 1   graph: 0     user_name
```

`tone` in the graph and not the tables is the first evidence of the graph knowing something the tables could not hold — [dialogue 06](06-one-memory-or-two.md)'s whole argument, showing up in real data. The other two rows are the blockers.

## Q1 — A name is a claim, and §9 was decided too early

**`user_name` is missing from every session**, and it is the most basic memory the tables hold. [ADR 0007 §9](../../adr/0007-the-relation-vocabulary-is-a-catalogue.md) stopped the extractor emitting name-claims, for a good reason: `self —name→ Guillermo` made *"Guillermo"* a **person node** sitting beside `self`, so one human became two nodes. It recorded the gap honestly:

> Where a name-claim goes instead. "The owner is called Guillermo" should **rename the `self` node** […] That route is a write path and this record does not open one.

**That route now exists** — ADR 0009 gave the graph `rename`. So the stated blocker is gone, and the obvious wiring suggests itself: the extractor renames the owner, the store emits the label as `user_name`.

**It is unsafe, and the reason is worth keeping.** A label carries no `origin`. `preferences_for` gates speech on `origin == "stated"` and is described as *the only thing in the system that reads assertions on behalf of a prompt*. Emitting a label would put extractor-inferred text in front of the model without passing that filter — the guarantee the agent's ADR 0017 rests on. And ADR 0009 is explicit that a label is a display name with **no history**, so there is nowhere to record who set it.

**The shape that works is the one [ADR 0008](../../adr/0008-preferences-are-assertions.md) already built.** A name should be a *claim*, not a label:

```
self —name→ "Guillermo"        dst kind: value · functional · key = the relation
```

Exactly the `tone` shape. It carries an origin, the existing filter gates it correctly, and it projects as a key without a special case.

**And §9's objection dissolves rather than being overruled.** It refused name-claims because the object became a **person**; as a `value` it is not a person at all but a string somebody is called — which is precisely the node kind ADR 0008 introduced, knowingly, for exactly this sort of object. **§9 was decided before ADR 0008 existed.** The record is not wrong; it is early.

The label still gets corrected — a graph whose owner is drawn as "self" is unreadable — but as a *consequence* of the claim rather than as the record of it, which is the split ADR 0009 already draws between what is true and what is drawn.

**Question**: amend ADR 0007 §9 to admit `name` as a preference-shaped relation to a value node, with the naming denylist becoming its aliases — or keep names out of the graph and accept that `user_name` is a key the tables keep forever?

## Q2 — Real memories live in the tail, and the projection cannot reach them

`has_dog: true` is in the tables. The graph holds `self —pet→ Canija`, which is **more** than the tables know — and cannot project it, because `claims_for` and `preferences_for` exclude tail relations. The reason is sound: a tail relation has no sentence, so there is no way to write it down for a model without inventing phrasing nobody approved.

The obvious answer is to promote `pet`, and **the catalogue's own admission test refuses it**. It is not functional — people have several pets — and its object has no kind: `_KINDS` is `person, organization, place, project, topic, value`, and a dog is none of them. `pet` is not a marginal case; it is a perfectly good relation the vocabulary cannot express.

So this is not a promotion. It is a structural fact: **the graph can hold things it may never say.** [Dialogue 06](06-one-memory-or-two.md) named that as a reason to unify the stores — *"the system knows things it may never say"* — and unification has reproduced it one level down, between the log and the projection rather than between two tables.

Three ways out, none free:

- **Accept it.** The tail is unspeakable by design and some memories stay in the tables. Step four never completes.
- **Give the tail a sentence.** A default rendering — *"self pet Canija"* — which is the invented phrasing §7 refused, and it would be the first text reaching a model that nobody wrote.
- **Widen the kinds.** `_KINDS` is a hard frozenset with no tail and no promotion path, so it is *stricter* than the relation vocabulary it sits beside. That asymmetry is itself unexamined: ADR 0007 gave `rel` a tail and a rule of three and left `kind` a closed six.

**Question**: which — and separately, does `kind` deserve the treatment `rel` got?

## Note

Steps one and two are built and **have never run as the primary store**: `graph_backed_memory` and `graph_retrieval_enabled` both default off and neither is set anywhere. The unification has been designed, implemented and never once exercised.

---

## Answers & agreed conclusions

### Q1 — Admitted, as `name`, and §9 was early rather than wrong

**Agreed 2026-08-26.** `name` joins the catalogue as a preference-shaped relation: `person → value`, functional, read as *"<src> is called <dst>"*, with the naming denylist becoming its aliases.

**The objection is answered, not overridden.** §9 refused a name-claim because *"Guillermo"* became a **person node** beside `self`, so one human was two. As a `value` it is not a person but a string somebody is called — the node kind [ADR 0008](../../adr/0008-preferences-are-assertions.md) introduced knowingly for exactly this sort of object, and which did not exist when §9 was written.

**It prevents the split rather than repairing it**, which is the stronger result. Today a name-claim mints a person node that then needs `same_as` to rejoin — the merge [A5](05-what-building-it-taught.md) calls unrecoverable. As a value, no person node is created at all.

**`functional` looked wrong and is right.** People have nicknames and formal names, and `alternative_name` was among the observed rows — so *"one name"* reads false. But functional means *at most one `dst` per `(user, src)` at a time*, and the question this relation answers is **what do I call you now**, which has one answer: "call me Gui" should *replace* "Guillermo", which is what a functional relation does and what a keyed memory does. Alternative names are a different relation and nothing has asked for one.

So it passes the admission test on functionality **and** on an asymmetric kind signature — a better case than `mother`, which earns its place on functionality alone.

**The denylist disappears**, and that is worth more than the feature. `_NAMING_RELATIONS` is described in its own docstring as *"a denylist, which is the shape this package argues against everywhere else […] used here because the alternative is worse rather than because it is good."* Those twelve words become aliases of a catalogue entry, and the one construct the vocabulary design had to apologise for goes away.

**Three costs, accepted.**

The key becomes `name`, not `user_name`. The relation name is the key, and `user_name` presumes the owner — wrong in a graph where any person may have one. **Nothing in the codebase reads it**: a grep over both packages and the console finds it only in the live database, so it was a key the model invented and a table accepted rather than one anything depends on. `memory-diff` will report both until the table rows age out.

It depends on the model emitting `kind: "value"` for a name — [B1](05-what-building-it-taught.md)'s *asked and cannot be held to*, for the fourth time. The kind signature is the backstop: a `name` claim whose `dst` is a person is dropped, which is exactly today's behaviour. **The failure mode is the status quo, not a wrong node.**

And it amends a record eight days old. The amendment says §9 was *early* — it reasoned correctly from what existed, and what existed changed underneath it.

### Q2 — Three answers, and the first is that the question was wrong

**Agreed 2026-08-26.**

**`pet` does not fail the admission test; it has nothing to be tested by.** Q2 above says it fails on both counts and that is half wrong. ADR 0007 admits a relation on functionality **or** an asymmetric kind signature, and `person → animal` *is* asymmetric — it catches an inversion outright. What blocks `pet` is that `_KINDS` has no `animal`, so there is no signature for the check to use. **The relation vocabulary is blocked by the kind vocabulary**, and the kind vocabulary is the one with no growth path.

**`kind` does not get a tail, and the reason is principled rather than cautious.** `node_named(user_id, kind, label)` means **kind participates in identity**. A drifting relation makes a junk edge that can be ignored; a drifting kind makes a *duplicate node* — `person:Canija` and `animal:Canija` are two things, and one thing has become two. Rejection at the door is right when the cost of acceptance is a split identity and wrong when it is a junk edge, so ADR 0007's argument does not transfer wholesale. It was reasoning about a field that does not name anything.

**The gap it leaves is evidence, not permissiveness.** The relation tail exists so the vocabulary can grow *from what actually arrived*. `kind` has no equivalent: `_clean()` returns `None` for an unknown kind, which increments `dropped` next to malformed JSON and self-referential claims. So nobody can tell which kind to add, because nothing records that `animal` was refused eleven times. The answer is to **count the refusals** — the same rule of three through a different mechanism, because the cost of a wrong acceptance differs. See Q3.

**`has_dog` was never a missing memory**, and this is the part worth keeping. It is a **key**; `self —pet→ Canija` is a **claim**. `pet` is not a preference — its object is a thing rather than a word — so even fully admitted it would surface through `claims_for` as a retrieval candidate and never as keyed memory. `memory-diff` flags it because it compares *keys*, and the graph holds the fact more precisely by a different route.

That is not a gap to close. It is the two stores being different shapes, which is what [dialogue 06](06-one-memory-or-two.md) said from the start — and it means **step three was never blocked by `has_dog`.** `user_name` was the only real blocker, and [Q1](#q1--admitted-as-name-and-9-was-early-rather-than-wrong) cleared it.

**Rejected outright: giving the tail a sentence.** A default rendering — *"self pet Canija"* — is the invented phrasing ADR 0007 §7 refused, and it would be the first text reaching a model that nobody wrote. Not a close call.

### Q4 — Three keys, and the clause that makes it three

**Opened 2026-08-26**, after both first-turn crashes were fixed and the graph-backed store finally served a turn. What is left is not a defect. It is that the store accepts **three keys** — `tone`, `language`, `name` — where the tables accept any, and that decides whether a person can live on it.

**The projection is already general. One predicate is not.**

```python
def preferences() -> tuple[Relation, ...]:
    return tuple(r for r in CATALOGUE if r.functional and r.dst_kind == "value")
```

Everything downstream handles any relation. `preferences_for` filters `claim.src != owner_node.node_id` — so *a key is a fact about the owner* is **already enforced**, by the projection rather than by the predicate. And `_preference` reads `labels.get(claim.dst)`: the dst node's label, whatever kind it is. Nothing below `preferences()` cares that a value node is a value node.

**So why `dst_kind == "value"`?** Its docstring says a key holds *"a word rather than a reference to something else in the graph"*. That is a real distinction and it is not the one that matters here: a reference has a label, and a label renders as text exactly as a word does. The value node's own admission ([ADR 0008](../../adr/0008-preferences-are-assertions.md)) was about giving a *word* somewhere to live, not about forbidding a reference from being a key.

**The test that seems right is `functional and src_kind == "person"`** — one answer, about the owner. Which gives:

| relation | today | proposed |
|---|---|---|
| `tone`, `language`, `name` | key | key |
| `employer`, `mother`, `father`, `lives_in` | claim only | **key** |
| `cto`, `ceo` | claim only | claim only — src is an organization |
| `same_as` | — | — not functional |

Seven keys, and they cover **five of the seven** keys real use produced: `user_name`→`name`, `tone`→`tone`, `mother_name`→`mother`, `employer`→`employer`, `location`→`lives_in`. The two that fall out are `acme_cto`, which is a fact about Acme rather than about the owner, and `dog_name`, which needs [Q2](#q2--three-answers-and-the-first-is-that-the-question-was-wrong)'s missing kind.

**Why `src_kind` and not `functional` alone.** `_write` hangs every key off the owner node, so admitting `cto` would let `remember(key="cto", value="Diane")` write `self —cto→ Diane` — the owner as an organization, which the kind signature exists to prevent. The projection would then never return it, because no `cto` claim hangs off the owner, so the tool would advertise a key that silently does nothing. Excluding it by predicate rather than by accident is the difference between a rule and a coincidence.

**What it costs.**

A key's value becomes a **node label**, and labels change: `rename` would silently change what a memory says. That is arguably right — if Claudia is renamed, *"your mother is Claudia"* should follow — but it is the first time a memory's value is not the value that was written.

`_write` must mint the dst with `relation.dst_kind` rather than the hardcoded `"value"`, which means **the memory tool can create person, organization and place nodes**. It could previously only create values. `refer_to` matches exactly on a normalized label and can only fail to find, never conflate, so [A5](05-what-building-it-taught.md)'s asymmetry still holds — but the model naming a person now mints an entity, and that is a widening worth saying out loud.

And it amends [ADR 0008](../../adr/0008-preferences-are-assertions.md), which chose that predicate deliberately.

**Question**: widen `preferences()` to `functional and src_kind == "person"`, or keep three keys and accept that most of what a person says is a claim awaiting confirmation?

### Q3 — Should refused kinds be counted?

Falls out of Q2 rather than being asked independently.

`bacteria-admin relations` reports relation names the extractor keeps producing and the catalogue lacks, reading a `GROUP BY rel` over the log. There is no sibling for kinds, and there cannot be the same one: a refused kind never reaches the log, because the claim carrying it is dropped whole.

So it needs somewhere to be counted — a tally of refusals rather than a query over what was written. Small, and it makes `_KINDS` growable in exactly the way `rel` already is: deliberately, top-down, from evidence about what arrived.

**The cost worth naming**: a refusal tally is a second place data accumulates, with its own retention question and no viewer — which is what [07's Q1](07-relation-vocabulary.md) argued against when it kept the relation tail *in* the graph rather than in a side table. The difference is that this holds counts rather than claims: nobody's facts, no provenance, nothing anyone could be shown. That may be enough to make it a different thing, and it may not.

**Question**: build the tally, or leave `_KINDS` frozen and let a kind be added the day somebody notices they need one?

### Q4 — Do not widen. Three keys is right, and a live run says so

**Agreed 2026-08-28, and it settles against the proposal in the question.**

**Widening would re-create the tables' behaviour inside the graph.** A keyed memory is *always in the prompt*. The tables put everything there because they had no other mechanism; the graph has one — [ADR 0011](../../adr/0011-a-confirmed-fact-may-be-spoken.md) made a confirmed fact a retrieval *candidate*, surfaced when the message is about it. So `preferences()` selecting only preferences is not an accident of one clause. It is the split: **preferences always, facts on demand.**

Making `mother` a key would put it in every prompt, which is what [§14](../../architecture/memory-graph.md)'s bet says loses to relevance. The proposal reached parity with the tables by adopting the behaviour the thesis calls worse.

**Which reframes the "regression".** Seven keys to three is not a loss: five of those seven were *facts that should never have been always-on*. The tables held them that way because they could not do better.

**And the name was the tell.** A function called `preferences()` returning `mother` is a misnomer — the anti-pattern [§10](../../architecture/memory-graph.md) lists by name. The concept would have changed, not just the predicate, and a predicate change dressed as a small one is how a vocabulary drifts.

**`name` was right to widen and this is not the same move.** The test is *would you want this in every prompt*: a name passes, because it is how you address someone; a mother's name does not. [ADR 0012](../../adr/0012-a-name-is-a-claim-about-a-value.md) holds and does not generalize.

#### The run

Turned on `graph_backed_memory` and `graph_retrieval_enabled` together, confirmed one `mother` claim through the write route, and asked three questions in fresh sessions:

| asked | claim | origin | answered |
|---|---|---|---|
| what is my mother called | `self —mother→ Claudia` | **stated** | *"Your mother is called Claudia."* |
| where do I work | `self —employer→ Acme` | **stated** | *"You work for Acme."* |
| where do I live | `self —lives_in→ Madrid` | inferred | *"I don't know where you live."* |

Neither relation is a key. Both surfaced. The unconfirmed one did not — so the `origin == "stated"` gate holds on the live path and not only in tests.

#### What it does not prove, which matters more

**None of those questions contained a node label**, so anchor resolution found nothing — and with no anchor the supplier returns *everything confirmed*. There are five confirmed claims, so "everything" and "the relevant ones" were the same set.

**The plumbing is proven; the bet is not.** Whether narrowing beats not-narrowing is still untested and still wants volume, because at this scale there is nothing to narrow. That is the same conclusion [dialogue 06's correction](06-one-memory-or-two.md) reached from the sequencing, and [Q2](#q2--three-answers-and-the-first-is-that-the-question-was-wrong) reached from the tail — **three independent routes to one place**, which is either a well-founded conclusion or a project talking to itself, and the difference is settled by data nobody has yet.
