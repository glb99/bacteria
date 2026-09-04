# Dialogue 02 — Gaps found by the worked example

> Source: [`prototypes/01-worked-example.md`](../prototypes/01-worked-example.md), 2026-08-22. Tracing four weeks of realistic input through the agreed v1 model exercised every mechanism; these five holes are what it found. Unlike dialogue 01's questions — which were about *scope* — these are all about **operational policy**: the model says what exists, and is silent on when things run and who authors them.

## F1 — Who authors constraints?

The worked example's week-3 contradiction only fired because a constraint "Organization has one CTO" existed. Nothing in the model explains where it came from.

§10 gives a growth doctrine for **types** (bottom-up evidence, rule of three, top-down ratification) and says nothing about **constraints**. But the user will never author them — they don't think in functional properties and disjoint classes, and §2 says they shouldn't have to.

So: does the agent propose constraints from observed regularity? If it does, how does it distinguish a real invariant from a coincidence — is there a rule-of-three equivalent? And what's the failure cost: a wrongly-inferred constraint generates false contradictions forever, which is worse than having no constraint at all.

## F2 — When does staleness re-derive?

§6 defines staleness propagation but never says when re-derivation runs. The options have very different characters:

- **Eagerly**, on every assertion change — correct but expensive, since each re-derivation is an LLM call, and a single revision can touch many conclusions.
- **Lazily**, on read — cheap, but the user may look at the graph and see a conclusion the system already knows is stale.
- **Batched**, on a schedule or alongside the §10 refactoring chore — probably the pragmatic answer, but it needs a staleness *queue* and a policy for what jumps it.

This is the difference between a memory that self-corrects and one that merely knows it is out of date.

## F3 — Are evidence links pinned to assertion versions?

The trace only worked because conclusion `c1` recorded *which* assertions it used. Palantir's phrasing is that lineage captures a decision made "atop which version of enterprise data."

§6 lists evidence links but never states they are pinned to a specific assertion *version*. If they aren't, week 4's revision silently rewrites what week 2 believed, and the bi-temporal protection from §3 evaporates exactly where it was supposed to help.

Likely answer: with an append-only log an assertion is already immutable, so evidence links pin naturally — but this needs saying explicitly, and the projection layer must not resolve them to "current" behind the scenes.

## F4 — Cold start inverts the interruption budget

§8's risk-weighting assumes steady state. But merge proposals cluster at the beginning, when every name is new and everything is ambiguous — precisely when the user has the least context to judge and the least patience for a queue.

Do confidence bands adapt as the graph matures? Do early merges batch until there is enough signal to decide several at once? Or does the event-storming onboarding ritual (§8) front-load enough identity to avoid the pile-up?

## F5 — What does `possibly-same-as` mean to everything else?

§8 introduced it as a first-class representation of unresolved identity, which is right. But nothing says how the rest of the system reads it:

- Do derived properties compute over the union of the two candidates, or separately?
- Does "show me everyone at Acme" return one node or two?
- Can a conclusion cite an assertion about one candidate as evidence about the other?
- Does the graph draw one node or two?

**Uncertainty the query layer cannot interpret is uncertainty that leaks.** Whatever the answer, it has to be consistent across derivation, query, conclusion and rendering.

---

## Answers & agreed conclusions

**(2026-08-23) F3 — Evidence links pin to assertion identities: RESOLVED as a side effect of [R1](03-bacteria-reconciliation.md).**

R1 gave assertions a surrogate identity of their own, distinct from the triple they state, because the alternative — keying an edge by `(owner, src, rel, dst)` — cannot represent a relation believed, retracted and believed again. Evidence links pin to that identity, so a later revision creates a new assertion rather than rewriting the premise a past conclusion cited. The suspicion recorded in F3 was right: with an append-only log the pinning is natural. What was missing was the *identity* to pin to, and a current-state primary key would have silently denied it. The projection layer must not resolve evidence links to "current" behind the scenes.

**(2026-08-23) F5 — `possibly-same-as` is resolved by consumer, and citing across it makes the link itself evidence: AGREED**

Three of dialogue 03's decisions narrowed this before it was discussed: assertions are addressable ([R1](03-bacteria-reconciliation.md)), prompt text is confirmed-only while the graph may hold more (R3), and conclusions carry mandatory evidence links (R4).

**Both obvious answers fail.** *Union semantics* — one entity until disproven — silently asserts the very thing we declined to assert, and makes the separate band pointless, since it would then behave identically to `sameAs`. *Separation semantics* — two until confirmed — never over-claims but leaves the system knowing something it refuses to act on, answering "everyone at Acme" with an apparent duplicate and no explanation.

**The resolution splits by consumer**, using R3's asymmetry: what a human sees may be richer than what a model is told, and the three consumers have genuinely different capacities.

| Consumer | Behaviour |
|---|---|
| **Storage** | Always two. Nothing merges, ever — §3 already links identities rather than merging entities, and even a confirmed `sameAs` yields a projection |
| **Derivation** | Computes **separately, per entity**. Derived properties are deterministic logic (§5) and must never rest silently on an unratified guess. A computation over the union is a **conclusion, not a derivation**, because it rests on a judgment — which is exactly the line §5 was drawn for |
| **Prompt text** | **Both, with the uncertainty in prose**: "Diane — possibly the same person as Diana Mercer." Suppressing one lies by omission; merging asserts something unratified |
| **Rendering** | Two nodes, dotted link, merge affordance — as in the worked example's week 2. Ambient, never nagging; §8 makes it a permanent statement, not a to-do |

**The finding that answers F5's own framing.** F5 ended "uncertainty the query layer cannot interpret is uncertainty that leaks." The answer is that **the query layer should not interpret it**. A graph query language cannot represent "these might be the same"; a language model reads that sentence and reasons correctly with it. The LLM is the one consumer that handles ambiguity natively, so the uncertainty is *passed through* rather than resolved before it arrives.

**The rule that makes cross-candidate reasoning safe:**

> A conclusion may cite evidence across a `possibly-same-as` boundary — but doing so makes that link part of its evidence.

Mechanically free, since by R1 the link is an assertion with an id, so citing it is identical to citing any other. The payoff is automatic: reject the merge later and staleness propagation (§6) fires on every conclusion that leaned on it. Cross-candidate reasoning becomes *allowed but tracked* rather than forbidden or silently wrong — and without the rule, rejecting a merge leaves quietly-broken conclusions with nothing pointing at them.

**Two rules fall out:**

- **Symmetric, explicitly not transitive.** A~B and B~C does not yield A~C, because confidence does not compose — two 0.6 links do not make a 0.6 link. This is concrete: the constraint kernel has a `transitive` construct and `sameAs` uses it; `possibly-same-as` must be excluded from it.
- **Rejection is recorded as a fact, not a deletion.** Confirming appends `sameAs`; rejecting appends `distinctFrom`; both close the `possibly-same-as` recorded interval. If rejection merely deletes, the same similarity re-proposes the same merge next week forever — the failure mode that makes a review queue unusable, and adjacent to F4.

**Cost, accepted**: derivations computing separately mean "days since last contact" is wrong for both candidates until someone merges them. Mitigated by the dotted link rendering wherever they appear, so the user sees why the number looks odd, and the fix is one click.

**F1, F2 and F4 remain open.** They are the three that a running system answers better than a discussion can — respectively: whether the agent can propose constraints without inventing rules from coincidence, when re-derivation runs, and how merge proposals behave before the graph has a spine.
