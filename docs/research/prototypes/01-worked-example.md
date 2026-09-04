# Prototype 01 — A worked example, end to end

> **Purpose**: the v1 model in [MENTAL-MODEL.md](../../architecture/memory-graph.md) was agreed in the abstract. This traces one realistic sequence of personal input through it to find where it holds and where it breaks. Written 2026-08-22. Not code — a hand-simulation.
>
> **Result**: the mechanisms compose better than expected, but the trace surfaced **five genuine gaps**, listed at the end and promoted to [`dialogues/02-open-gaps.md`](../dialogues/02-open-gaps.md).

## Scenario

Four weeks of ordinary input, chosen so that between them they exercise identity resolution, contradiction, constraint negotiation, schema promotion, late-learned facts and staleness propagation.

| When | Input |
|---|---|
| Week 1 | *"Had coffee with Diane from Acme — she's their CTO, we talked about the integration."* |
| Week 2 | Email arrives from `Diana Mercer <diana@acme.com>` about a proposal |
| Week 2 | *"Diane's also advising Beltran on their data platform."* |
| Week 3 | A newsletter says *"Acme CTO Bob Restrepo announces…"* |
| Week 4 | *"Actually Diane left Acme back in February."* |

---

## Trace

### Week 1 — first contact

Extraction proposes two entities and a relation. All three are additive, low-stakes and clearly sourced, so per §8 they **auto-commit**; nothing interrupts.

```
a1  assert Person{name:"Diane"}                valid[?..]      recorded[W1]  src:conversation
a2  assert Organization{name:"Acme"}           valid[?..]      recorded[W1]  src:conversation
a3  assert role(p1 → o1, title:"CTO")          valid[?..]      recorded[W1]  src:conversation
a4  assert Event{type:Meeting, participants:[me,p1], topic:"integration"}
```

Note `valid[?..]` — the conversation gave no start date. **The model tolerates unknown valid-time**, which turns out to matter in week 4.

The meeting is an Event object, not an edge, straight from the §4 test: you can point at it and call it a thing.

### Week 2 — the identity question

`Diana Mercer <diana@acme.com>` arrives. Name similarity plus shared organization puts this in the **medium confidence band** (§8): not an exact-identifier match, not a wild guess.

So the agent proposes a merge and it **stages**. This is the right place to spend the interruption budget — rare, consequential, and the user answers in half a second. The graph draws two nodes joined by a dotted link with a diff of what would combine.

User accepts. Crucially this asserts `sameAs`, it does not destroy:

```
a5  assert Person{name:"Diana Mercer", email:"diana@acme.com"}  recorded[W2]  src:email
a6  action MergeIdentities(p1, p2) → assert sameAs(p1,p2)       actor:user    ratified[W2]
```

Both observation sets survive underneath; the merged person is a projection; `a6` is retractable. Had the user hesitated, the fallback is `possibly-same-as` as a permanent statement of uncertainty rather than a nagging to-do.

### Week 2 — the advisory relation, and a type is born

*"Diane's also advising Beltran"* creates an edge with a scalar property. Fine on its own.

But the agent has now seen this shape three times — an earlier advisory arrangement of the user's own, one noted for a colleague, and now Diane's. **The rule of three fires** (§10), and it fires as *two* proposals at once, which is where §4's promotion rule and §10's schema ratchet meet:

> Proposed: promote `advises` from a link property to an **`AdvisoryEngagement` event type** (advisor, client, scope, start, end).
> Reason: seen 3×; each instance is accumulating properties beyond a scalar.

This stages, because type changes are structural. The user accepts, and the three existing edges migrate.

**This is the moment the ontology grew itself, correctly, without the user ever having authored a type.**

### Week 2 — a conclusion, with evidence

The agent concludes something not directly stated:

```
c1  Conclusion{
      statement: "Diane is the decision-maker for the Acme integration",
      subject:   [p1, o1],
      evidence:  [a3 (CTO role), a4 (met about integration), a5 (initiated proposal email)],
      confidence: 0.72,
      derivedBy: llm-judgment,
      status:    active,
      recorded:  W2
    }
```

Per §6 the evidence links are mandatory, and per §5 this is a conclusion rather than logic, because an LLM produced it.

### Week 3 — contradiction, not correction

The newsletter says Bob Restrepo is Acme's CTO. This conflicts with `a3`.

Per §8 the system **flags rather than rejects**. Both assertions land, both keep provenance, and the conflict becomes visible:

```
a7  assert role(p3:"Bob Restrepo" → o1, title:"CTO")  recorded[W3]  src:newsletter
!!  conflict: functional constraint "Organization has one CTO" violated by {a3, a7}
```

The graph shows a contradiction badge on Acme. Nothing is silently overwritten, and the user isn't interrupted — the world is genuinely ambiguous right now, and the model is allowed to say so. **This is the honest-messy-model principle earning its keep**: a system that resolved this automatically would have picked one and been wrong half the time.

### Week 4 — the late-learned fact, and the cascade

*"Diane left Acme back in February."* This is the interesting one, because it is **bi-temporal**: recorded in week 4, valid from February — *before* everything above.

```
a8  assert endOf(a3.role) valid[Feb]  recorded[W4]  actor:user  ratified
```

Three consequences fire, in order:

**The contradiction resolves itself.** Bob became CTO when Diane left; `a3` and `a7` no longer overlap in valid time. The conflict badge clears with no user action. *The contradiction was never an error — it was a missing time boundary.*

> **Correction (2026-08-23), from [`02-executable-trace.py`](02-executable-trace.py).** This paragraph is wrong as written. `a7` has an unknown start too — the newsletter never said when Bob became CTO — so closing Diane's role at February leaves Bob's interval still reaching backwards over it, and the badge stays lit. The conflict clears only if the system *assumes* the successor began when the predecessor ended, which is a judgment, not an observation. Per §5 that makes it a conclusion carrying evidence, not a derivation. See [`dialogues/04-executable-findings.md`](../dialogues/04-executable-findings.md) E1. Left uncorrected above so the mistake stays visible: a hand-simulation supplies the intent the reader already has.

**Staleness propagates.** Walking evidence links from `a3` reaches `c1`, which is marked `stale`. Not *wrong* — stale.

**And this is where bi-temporality pays for itself.** `c1` was drawn in week 2 from what was known in week 2. It was a *correct inference from a stale premise*, not a bad inference. The two time axes let the system say so: the conclusion was valid in recorded-time and false in valid-time. Without both axes you cannot distinguish a reasoning failure from a late discovery, and the agent would either look incompetent or learn the wrong lesson from its own history.

---

## What held up

- **Auto-commit versus staging fell out cleanly.** Across the whole trace only two things interrupted the user — one merge and one type promotion — and both were worth it. Every fact flowed through silently. The risk-weighting from §8 appears to be tuned correctly.
- **The three promotion rules never conflicted.** Meeting→Event, advisory→Event, contact details→struct, capability→interface: the "is it a thing?" test decided every case without ambiguity.
- **Flag-don't-reject was vindicated by week 4.** Had the system forced a resolution in week 3, it would have destroyed a true assertion. The contradiction was information, and it resolved itself once time boundaries arrived. — *Half right. Executing the trace showed the contradiction does not resolve itself, and that it only fires at all under one unchosen reading of an unknown bound. See the correction above and [`dialogues/04`](../dialogues/04-executable-findings.md).*
- **The rule of three produced a genuinely good type** that the user would never have thought to define in advance.
- **`sameAs`-not-destroy meant the merge was never scary.** Nothing in the trace required the user to make an irreversible call.

---

## Findings — five gaps

Each is a real hole, not a detail. Promoted to [`dialogues/02-open-gaps.md`](../dialogues/02-open-gaps.md).

**F1. Nobody authors constraints.** The week-3 conflict fired on "Organization has one CTO" — but where did that constraint come from? §10 gives a growth doctrine for *types* and says nothing about constraints. The user will never sit down and write them; they don't think in functional properties. Does the agent propose constraints from observed regularity, and if so, how does it avoid inventing rules from coincidence?

**F2. Staleness has no trigger policy.** §6 defines the mechanism but not when re-derivation happens. Eagerly on every assertion change (expensive — each is an LLM call)? Lazily on read (the user may see stale conclusions)? Batched? This is the difference between a memory that self-corrects and one that merely knows it's out of date.

**F3. Conclusions need their own bi-temporality, and we only half-specified it.** The trace only worked because `c1` recorded *which assertions* it used. Palantir's phrase is "atop which version of enterprise data." Our §6 schema lists evidence links but never says they are pinned to assertion *versions*. Unpinned, week-4's revision silently rewrites what week-2 believed.

**F4. Cold start inverts the interruption budget.** Merge proposals cluster at the beginning, when everything is ambiguous — exactly when the user has least context and least patience. §8 assumes a steady state. Do confidence bands adapt over time, or do early merges batch until there's enough signal to decide several at once?

**F5. `possibly-same-as` has undefined semantics for everything else.** If Diane and Diana are only *possibly* the same, do derived properties compute over the union or separately? Does "show me everyone at Acme" return one node or two? §8 introduced the link as a first-class representation of uncertainty but never said how the rest of the system reads it. Uncertainty that the query layer can't interpret is uncertainty that leaks.
