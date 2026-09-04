# Dialogue 15 — The third axis

> Opened 2026-08-31 by the human, after settling that the architecture domain wants one ontology rather than several:
>
> *"imagine we wanted to refine the way the current architecture ontology, by for example in a 3d graph, making the layers separating the components by hierarchy, and use 3d models for representing the database, the components, the features… in a consistent and more realistic and visual way"*

The question sounds like a rendering question and mostly is. What makes it worth a dialogue is the small part that is not: **a layered picture needs to know which layer is above which, and nothing in the ontology says.** Everything else the scene would need already exists, and two of the decisions it would face have already been taken — in the renderer, in comments, without the ontology being told.

## The measurement

The 2D console already draws most of this. Reading `frontend/src/architecture.ts` (724 lines) before proposing anything turned up three facts that change the shape of the question.

**The vertical axis already exists, and it lives in the renderer.**

```ts
function layerOf(names: string[], edges: Edge[]): Map<string, number> {
  const depth = new Map(names.map((n) => [n, 0]));
  for (let pass = 0; pass < Math.min(names.length, 12); pass += 1) {
    // relax: an importer sits one band above what it imports
```

Forty lines, no library, iterative relaxation rather than a topological sort, with the reason stated: *"a real codebase has cycles and a sort would either refuse or need a cycle-breaking pass. The bound is what stops a cycle spinning; the cost of being wrong inside one is that two mutually-dependent packages land on the same band, which is the honest picture anyway."*

So a depth per package is already computed on every render, from `imports` alone, and it is already correct about the hard case. A 3D view does not need to invent it. What it needs is the thing this function cannot produce: **whether that depth agrees with anybody's intent.** `layerOf` reports where a package *sits*; nothing reports where it was *supposed* to sit.

**The stated/derived split is already the drawing rule, and it is the reverse of the obvious one.**

```ts
// Shape carries what was *stated*, line style carries whether anybody has
// agreed to it, and the text below carries what was *derived*. Splitting it
// that way is the whole point: the picture stops describing the parser and
// starts describing the model people are building.
```

And the rejected alternative is recorded next to it: the scene used to pick a glyph from `tables > 0`, a derived property, *"so a package you had agreed was a feature looked identical to one you had rejected. The only knowledge anybody contributed reached the cards and never the picture, which is backwards for a surface whose whole argument is that stated and derived facts must not be drawn alike."*

This matters because the intuitive proposal — a cylinder for a database, a box for a package, shapes taken from the derived `kind` — is exactly the design this file already tried and abandoned. Any 3D scene inherits that ruling or overturns it deliberately.

**A third dimension cannot be hand-rolled, and the console's dependency budget is one.** The module's own opening: *"Hand-rolled SVG, no layout library. The console has exactly one runtime dependency and [dialogue 10](10-a-place-to-stand.md) decided a graph-drawing package runs hard against that grain — so the layering below is forty lines rather than a bundle."* Forty lines of SVG has no equivalent in WebGL. This is `three.js` or it is not 3D.

**What the ontology holds today**, for reference — five relations, five kinds, three classifications:

| | |
|---|---|
| derived | `imports` (module→module), `owns_table` (module→table) |
| stated | `is_a`, `is_not_a` (→`kind`), `same_as` (rename) |
| kinds | `module`, `package`, `table`, `word`, `kind` |
| classifications | `feature`, `layer`, `role` |

Nothing in that table orders anything. `is_a layer` says a package *is* a layer; there is no relation that says one layer is above another.

## Questions

### Q1 — Is `above` a relation, and between what?

The one genuine ontology change on the table. `layerOf` derives where things sit; a stated ordering would say where they belong, and **the gap between the two is a boundary violation you could see** — a package whose derived depth contradicts the stated order draws an arrow pointing up. That would make `checks.py` visible rather than tabulated, which is the strongest argument for building any of this.

The design question is what it relates:

1. **Between words** — `domain above infrastructure`. Layers are tier-three vocabulary, promoted by recurrence, and a word is already a kind. Three or four assertions describe the whole codebase, and they survive every package being renamed. But it only orders packages that somebody has already classified, and today most are unclassified — so the axis would be undefined for most of the tree, and the scene would fall back to `layerOf` for the rest, mixing two sources of height in one picture.
2. **Between packages** — `bacteria.app.architecture above bacteria.app.graph`. Direct, always applicable, and needs no classification first. But it is O(packages²) statements to say what four words would say, and every rename or split invalidates a batch of them.

The counterweight to both: **`imports` may already be the answer.** If a package's stated layer is only ever "the one its imports put it in", then `above` records nothing new and the honest move is to draw `layerOf`'s output and stop. The case for the relation rests entirely on intent and derivation being able to *disagree* — which is worth checking against the real repository before building it, because if they never disagree here the relation has no first user.

### Q2 — Is a pinned position testimony?

Layout is derived, and `derive.py`'s opening argument applies to it unchanged: repeatable, therefore storing it is *"a cache pretending to be a memory."* Coordinates, colours and mesh names do not go in the graph, and a stored `x,y,z` would go stale the moment a package is added and then silently lie.

But a position a **person drags and pins** is not derived. Nobody can re-derive why they moved `auth` to the front, and that is the exact test the log exists to apply — unrepeatable, so the row is the only record.

So: does a pin get an assertion, with `stated_by`, a retraction, and a supersede when they move it again? It would be the third instance of [dialogue 10 Q4](10-a-place-to-stand.md)'s split, which is either a sign the split is real or a sign it is being applied where it does not belong.

**What argues against.** A pin is about a *view*, not about the codebase. Every other row in that log is a claim about the world that could be right or wrong; a pin cannot be wrong. Putting it in the same table makes `current()` return a mixture of beliefs and furniture, and every consumer then filters. The cheap alternative is browser-local storage, which loses the pin across machines and has no author — acceptable for furniture, not for a claim.

### Q3 — Does the third axis earn a runtime dependency?

Dialogue 10 refused a graph-drawing library and the refusal produced forty legible lines. 3D has no forty-line version, so this question is *"is the layered view worth `three.js`"* and cannot be dodged by scoping the feature down.

The honest framing is not 2D-versus-3D but **what the third axis buys that the current bands do not already deliver.** The console already stacks packages into rows by depth. A z-axis buys occlusion, orbiting, and volume; it costs a dependency, a build-size step change, and a picture that is harder to screenshot into a dialogue. The strongest pro-3D argument is the one from Q1 — a violation as an arrow pointing *up* is legible in a way a red edge in a flat band diagram is not — and that argument needs Q1 answered first.

### Q4 — Does the drawing rule survive more channels?

Today: **shape = stated, line style = verdict, text = derived.** The scarce channel was assigned to testimony on purpose.

3D adds channels — volume, material, ground, scale, shadow — and abundance is what usually breaks a rule like this, because there is suddenly room to draw everything and no forcing function to choose. Two specific cases the scene would have to rule on:

- **The database.** A cylinder for a table is the most natural mesh in the vocabulary and it is *derived* (`owns_table`), which the current rule sends to the text label. Either the rule gets an exception for kinds that have a universally-read glyph, or the database does not look like a database.
- **The orphan.** A judgment about a package the parse no longer produces has nothing under it — and *floating with no ground* is a genuinely 3D way to say that, unavailable in the flat view, and entirely faithful to the stated/derived rule. This is the one place the extra dimension adds a sentence rather than an ornament.

The open question is whether a fourth and fifth channel get assigned by the same discipline or by whatever looks good, and the answer should be written down before the first mesh is.

---

## What is agreed

### Q1 — `above`, stated, between packages classified `layer`

**Agreed 2026-08-31.** The counterweight in the question — *`imports` may already be the answer* — was checked against the repository rather than argued, and it does not survive.

**The derived axis collapses on the only codebase we have.** `layerOf`'s algorithm over the real package graph, grouped as the console groups it:

```
  0  bacteria.agent, bacteria.app, .entrypoints, .repositories
  1  bacteria.app.evaluation, .models, .views
  2  bacteria.app.architecture
 24  bacteria.agent.runtime, app.auth, app.core, app.graph
 25  agent.context, agent.session, agent.tools, app.ingestion, app.personal
 26  bacteria.agent.model
```

Nineteen packages, fifteen of them in three adjacent bands at the ceiling. Two cycles cause it — `core <-> ingestion` and `core <-> personal` — and the relaxation pumps everything reachable from them to the bound.

That is worth stating precisely, because it inverts the argument. The function is not wrong; its own comment already conceded that a cycle puts mutually-dependent packages on one band and called that *"the honest picture anyway."* What the measurement adds is the **blast radius**: a cycle does not degrade the two packages inside it, it degrades every package downstream of it. So derivation fails hardest exactly where the picture would be most useful, and a stated order is not a refinement of `layerOf` but the only thing that produces an axis at all.

**Layers are packages, not free words**, which corrects option 1 as the question posed it. `classify.py` proposes `is_a layer` from fan-in with no roles carried, so the vocabulary is not `domain`/`infrastructure` but the packages themselves:

| | |
|---|---|
| layer (4) | `agent.model`, `agent.session`, `agent.tools`, `app.core` |
| feature (5) | `app.architecture`, `app.auth`, `app.graph`, `app.ingestion`, `app.personal` |
| unclassified | 6 of 15 multi-module packages |

Four layers is **at most six statements**, and two or three if they chain. That is the entire vertical axis, hand-stated, and it survives renames because `same_as` already carries subjects forward.

**Features are not ordered and do not need to be.** A feature sits above every layer it imports, which stays derived. One relation therefore covers all nine classified packages; the six unclassified ones are drawn ungrounded, reusing [Q4](#q4--does-the-drawing-rule-survive-more-channels)'s floating-orphan idea rather than inventing a second mechanism for "no known height".

**The payoff is a specific existing wart made visible.** `core -> personal` is a layer importing a feature. Under a stated order that is an arrow pointing *up* — the cost [dialogue 14](14-the-domain-with-no-package.md) recorded and deliberately left standing, drawn as a violation the first time the scene renders. The relation has a first user before it is built, which is the test dialogue 11 set for anything entering the catalogue.

**Two costs, recorded because they are real and neither is a reason not to build it:**

1. **`above` is the first relation whose validity depends on a *stated* classification of its endpoints.** Kinds live in the catalogue; classifications are judgments. So *both ends must be layers* is a rule in the writer, not a constraint `Relation` can express — a two-level testimony structure the log has not had before. Every prior relation could be validated against the meta-model alone.
2. **Retracting `core is_a layer` strands every `above` naming it.** The ruling is **do not cascade**: the log never deletes, and closing rows nobody closed would manufacture exactly the history it exists to refuse. The stranded assertions are reported as orphans instead — the machinery built in PR #92 for renamed subjects, doing a second job unchanged.

**Mechanics**, following existing precedent rather than choosing: not functional (a layer may be above several); chains followed at read time the way `renames()` follows them; a cycle broken rather than raised on, for the reason `renames()` gives — one contradictory pair must not take the whole surface down.

### Q2 — A pin gets no row, and the drag that mattered was never a pin

**Agreed 2026-08-31.** The question's own framing is corrected first, because it chose the wrong test.

**Unrepeatable is necessary but not sufficient.** The question argued a pin earns a row because nobody can re-derive it, quoting `derive.py`'s repeatable/unrepeatable split. That split decides what must not be *stored as a cache*; it does not decide what belongs in an **assertion** log. The log's real admission test is **contradictable** — it offers `retracted`, `expired` and `superseded`, and all three are meaningless for something that cannot be wrong. Two people pinning one node in two places are not in conflict; two people saying `core is_a layer` and `is_not_a layer` are, and surfacing that is the machinery's whole purpose.

That test alone would also exclude `tone` and `language`, which sit in the personal catalogue and are preferences. So the second half of the test: **does anything but the renderer read it?** Tone changes what the agent says, on a surface that did not record it. A pin changes pixels in the one view it was made in. Admitting it means every consumer of `current()` filters it out permanently, in exchange for one component's convenience.

**Three destinations, decided by what the drag meant:**

| the gesture | where it goes | why |
|---|---|---|
| dragging a package up or down | an `above` assertion — [Q1](#q1--above-stated-between-packages-classified-layer)'s relation | it is a statement about order, and the coordinate is re-derived from it |
| dragging it sideways | browser-local, no row | furniture; lost on another machine, which is the correct cost |
| saving a whole named arrangement | a table owned by `architecture/` | authored and kept, but it has no truth value, so not the log |

**The first row is the answer to most of the question.** Somebody dragging `core` below `personal` is not choosing a position, they are stating an order — so capture the claim and **discard the coordinate**. It then travels between machines, carries an author, and can be argued with, which is everything the pin-as-testimony argument actually wanted. Q2 largely dissolves into Q1, and the pin that remains is the one nobody would have defended.

**The counter, recorded because it is the strongest thing against this ruling.** A hand-arranged architecture diagram *is* a mental model made explicit, which is [`idea.md`](../README.md)'s founding thesis. If arrangements are collaborative — a team agreeing how they see the system — an arrangement is a claim about shared understanding and arguably the most valuable content in the repository. The ruling stands, because that log holds claims about a **codebase** and an arrangement is a claim about a **picture**. But it makes the third destination real rather than a consolation, and it argues for capturing the **reason** somebody arranged it so: that is testimony, contradictable, and it is the same missing artefact [dialogue 14 Q4](14-the-domain-with-no-package.md) named as architecture's one plausible route to durable sessions.

### Q3 — `three.js` is accepted, sequenced behind `above`, and does not replace the flat view

**Agreed 2026-08-31**, against the recommendation, which is recorded rather than quietly dropped.

**The recommendation was to refuse, and its argument was cost against scale.** Nineteen packages and about forty inter-package edges is a size WebGL is not for; the payoff [Q1](#q1--above-stated-between-packages-classified-layer) delivers arrives in the existing SVG for nothing; and an isometric projection of `(x, y, layer)` through a fixed matrix would give the slabs-with-things-resting-on-them reading with no library at all, since the `shape === "layer"` branch already draws a slab.

**The human accepted the dependency, and the counter-case is stronger than the recommendation allowed for.** Recorded because it is the reason, not a concession:

- **Orbiting disambiguates crossing edges**, and forty edges in a flat diagram cross a great deal. That is a real fix at this size, not one that waits for hundreds of nodes.
- **Legibility and pleasure of use are goals, not decoration.** This console is the negotiation surface the whole design bets on ([§14](../../architecture/memory-graph.md)), and a surface people enjoy opening is one they open.
- The cost is a few hundred kilobytes on an internal tool with no page-load budget to defend.

**What the dependency is, stated precisely**, because the question conflated two things. WebGL is the browser's low-level GPU API — shaders, buffers, matrices, no notion of a box or a camera — and nothing hand-rolls it for a diagram. `three.js` is the library above it. So there was never a middle option, and the earlier framing *"`three.js` or it is not 3D"* was the whole of the choice.

**This is also the first dependency taken on taste.** The console's one runtime dependency, `openapi-fetch`, is a typed client generated from the API contract — the contract boundary made concrete, not a library somebody preferred. Worth noting so that [dialogue 10](10-a-place-to-stand.md)'s budget is understood as *spent deliberately* rather than eroded.

**Three conditions, and the first is the one that matters:**

1. **`above` is built first.** Without it the 3D scene renders the same collapsed 24/25/26 axis as the flat one, only prettier — a broken order in three dimensions. Q1 is the prerequisite either way, and it is the small piece, so the layered picture can be read in the existing renderer before the engine is committed to.
2. **The SVG view stays.** Not preserved out of attachment: the flat view is what pastes into a dialogue, and this project's method runs on quoting evidence into markdown. Two views over one model, and the flat one remains the one that gets cited.
3. **The scene is a pure function of the model.** Every mesh, position and colour computed from `ModelOut` on each render, nothing stored. That is [Q2](#q2--a-pin-gets-no-row-and-the-drag-that-mattered-was-never-a-pin)'s ruling applied to the renderer — the moment geometry persists, the ontology has acquired a rendering concern and `above` stops being the source of the axis.

### Q4 — One principle, applied top-down, and both hard cases fall out of it

**Agreed 2026-08-31.** The rule survives, because it was never a rule about shape.

**What is underneath it:** the strongest perceptual channel goes to the **least recoverable fact**. Derived facts are recomputed on every render — lose one and you re-parse. Stated facts are the contribution and the only thing that can be lost. That generalises to any number of channels, where the existing formulation — *shape stated, line style verdict, text derived* — was a three-channel instance of it and would have had to be re-decided for every new channel.

Salience order in a scene runs roughly position → form → size → material → label, so:

| channel | carries | |
|---|---|---|
| vertical position | the stated `above` order | stated |
| form, between kinds | package, table, module | derived |
| form, within a kind | `feature` drum, `layer` slab | stated |
| material | verdict — solid agreed, ghosted proposed | stated |
| size, label | module count, table names | derived |

**The database case corrects the question, which was too broad.** What `architecture.ts` rejected was giving *a package* a glyph from `tables > 0`. A table drawn as **its own node** is a different matter: form distinguishing *kinds* is fine, because a kind is not contestable and nobody can disagree that a table is a table. The rule governs distinguishing **states of the same kind of thing**. Cylinder for a table node, yes; drum for a package because it owns tables, still no.

**The orphan case unifies with [Q1](#q1--above-stated-between-packages-classified-layer) rather than adding a mechanism.** Floating uses the position channel — but position carries the *stated* order, and an orphan has none because its subject is gone. So floating is the honest absence, not a competing use. The same holds for Q1's six unclassified packages, which have no `is_a layer` and therefore no place in the order. **Ungrounded means nobody has said where this belongs**: one meaning, three sources, no second mechanism.

**The violation costs no channel at all.** An upward arrow is what geometry produces for free when the stated order and the derived import disagree. That is the best evidence the assignment is right — the most important thing the picture says is a consequence of the layout rather than a colour somebody had to allocate.

**The sentence to carry forward, and it belongs in [§8](../../architecture/memory-graph.md) rather than in a TypeScript comment:** *give the most salient unspent channel to the least recoverable fact.* It is a claim about how ontologies should be shown, not about SVG.

### Q5 — What else belongs in this ontology, and what earns its own

**Raised and answered 2026-08-31 by the human**, after the scene was built:

> *"what about abstractions like the API, the database, the background jobs… Do they belong to another type of visualization/ontology or what?"*

It arrived as a drawing question and is the extent question the earlier ruling — *one ontology, many instances* — left open. Having a scene made it concrete: once packages, layers and tables are on screen, the next thing anybody wants to see is routes.

**The discriminator is not whether something is a different concept.** Every candidate here is one. It is whether it has **different subjects, a different adapter, and a different truth condition** — and a candidate must fail to be a new ontology by all three, not one. Routes fail all three; a deployment topology passes all three.

| tier | examples | why |
|---|---|---|
| same ontology, relations nobody has asked for | routes, declared jobs, columns, foreign keys | same subjects (modules), same adapter (`ast`), same truth condition (repeatable) |
| same ontology, a **second adapter** | the live database schema, a running service's OpenAPI | same kinds and subjects, different source — and they can contradict the parse |
| genuinely another ontology | runtime behaviour, deployment topology, ownership | different kinds, different derivation, true *sometimes* rather than always |

**The database is already in** — `table` is a kind, `owns_table` is a relation — and routes and jobs are **deferred rather than excluded**, which `derive.py` states in its own opening: *"Not built: Calls, classes, functions, routes and tests. All derivable from the same parse, and each answers questions nothing is asking yet."* Adding one is a field. That docstring is the ruling; this question only confirms it against a second reader.

**The middle tier is the valuable row, and it was not in the earlier answer.** `owns_table` is what the *source* says; introspecting the database is what is *actually there*, and in real life they disagree — a migration unapplied, a column dropped by hand in production. That disagreement is precisely what flag-rather-than-reject was built for and **has never had a second user**. Provenance already separates the two writers (`origin`, `trust`), so one subject carrying claims from two adapters is a shape the substrate supports today without a new relation. The same holds for a deployed route table read against the parsed decorators: the routes that exist against the routes that shipped.

**Where the API genuinely leaves this ontology** is its *contract* — what a route promises, who calls it, whether it is public. Those consumers live outside the repository, so no parse can reach them: it is testimony, and it answers a different question than *how is this codebase arranged*. Jobs split the same way. The declaration is a parse; how often, how long and what fails is traces, whose truth condition is statistical rather than static.

**The visualisation consequence follows from [Q4](#q4--one-principle-applied-top-down-and-both-hard-cases-fall-out-of-it) and needs no new rule.** Tier one needs no new view: form distinguishes kinds, a kind is derived and uncontestable, so a route or a queue takes its own mesh and joins the scene. Tier three needs its own, because **the axis means something else** — height here is the stated `above` order; in a deployment view it would be a network boundary, and in a runtime view there is no hierarchy at all and the axis is time. One scene across those would repeat the error the `ontology` column already makes in flattening ontology and instance.

**Build order, recommended and not yet ruled on:** routes first — one field, free from a parse that already runs, and it answers the question people ask constantly, *what does this package expose?* Jobs second. The live-schema adapter has the most upside and wants its own dialogue before code, because two adapters disagreeing about one subject is a decision about provenance rather than a parsing task.

---

## Closing note

The four opening answers turned on the same move, and it is worth naming because it was not planned: **each question was decided by making a stated fact and a derived fact disagree, and then asking which one the system would be sorry to lose.**

Q1 measured the derived axis and found it collapsed — so the order is stated. Q2 found that a coordinate cannot be contradicted and a rename can — so only one of them is a claim. Q3 kept the flat view because the *evidence* has to be quotable even when the pretty view is not. Q4 gave the strongest channel to the least recoverable fact, which is the same sentence a fourth time.

That also sharpens a line already in [§8](../../architecture/memory-graph.md): *"user-authored clusters are assertions, not UI state."* Q2 appears to contradict it and does not. A cluster asserts **membership** — these things belong together — which can be contradicted. A pin asserts a **coordinate**, which cannot. The two rulings are one rule: *the drag that means something becomes a claim, and the drag that is placement does not.* The §8 sentence was right and was missing its test; this dialogue supplies it.

[Q5](#q5--what-else-belongs-in-this-ontology-and-what-earns-its-own) arrived after the scene existed and tests the same rule from the other side: it asks which *derived* facts are worth deriving at all, and answers that a candidate joins the ontology unless it fails on subjects, adapter **and** truth condition together. The one addition nothing had noticed is that a second adapter over the same subject — the source schema against the live one — would give the conflict machinery a user it has never had.

**What is now unbuilt and specified**: `above` in `architecture/catalogue.py`, written only between packages classified `layer`, chains followed at read time, cycles broken, stranded rows reported as orphans through the machinery PR #92 already built. Everything else in this dialogue — the isometric or `three.js` scene, the arrangement table, the channel assignment — waits on that one relation, which is four statements' worth of vocabulary and the smallest piece here.

Related: [dialogue 10](10-a-place-to-stand.md) (substrate vs policy, and the dependency budget), [dialogue 11](11-the-name-and-the-tail.md) (tier-three vocabulary, which `layer` is), [dialogue 13](13-the-subject-changed.md) (derived subjects change under stated claims), [dialogue 14](14-the-domain-with-no-package.md) (a decision settled by the repository's own numbers).
