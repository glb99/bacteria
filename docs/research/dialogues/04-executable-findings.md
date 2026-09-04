# Dialogue 04 — What executing the trace found

> Source: [`prototypes/02-executable-trace.py`](../prototypes/02-executable-trace.py), run 2026-08-23. It replays the same four weeks as [`prototypes/01-worked-example.md`](../prototypes/01-worked-example.md), but as code, under three readings of an unknown temporal bound.
>
> Prototype 01 was a hand-simulation written by the same mind that designed the model, so it could improve the design but not falsify it. This is the first artifact in the repo that could return an answer nobody wanted. **It did.**

```
policy          infer   conflict fires at W3   clears at W4, no user action   c1 stale   state_at(W2)
open            False   PASS                   FAIL                           PASS       PASS
open            True    PASS                   PASS                           PASS       PASS
strict          False   FAIL                   PASS                           PASS       PASS
strict          True    FAIL                   PASS                           PASS       PASS
three-valued    False   undecided              FAIL                           PASS       PASS
three-valued    True    undecided              PASS                           PASS       PASS
```

The two mechanisms nobody doubted — the staleness walk and `state_at` over recorded time — pass under every reading. **Everything involving valid-time overlap depends on a choice the model never made.**

## E1 — "The contradiction resolves itself" is false as written

Prototype 01's most-quoted line: *"Bob became CTO when Diane left; `a3` and `a7` no longer overlap in valid time. The conflict badge clears with no user action."*

It does not, and the reason is obvious once code has to do it: **`a7` has an unknown start too.** The newsletter never said when Bob became CTO. Closing Diane's role at February leaves Bob's interval still reaching backwards over it, so the two still overlap and the badge stays lit — the `open/False` row above.

The conflict clears only with `_infer_successor_starts`: assume the successor began when the predecessor ended. That is what a human does automatically, and it is **an assumption, not an observation** — there may have been a gap with no CTO, or an overlap during a handover.

By §5's own line, an inference resting on judgment is a **conclusion, not a derivation**. So the honest version of week 4 is: the badge clears *because the system concluded something*, that conclusion carries evidence, and it can be wrong and be retracted.

**Question**: is constraint-driven boundary inference in the model at all — and if so, is it a conclusion with evidence, as §5 implies?

## E2 — The week-3 contradiction fires only under one reading

Under `strict`, the conflict **never fires**. §8's showcase moment — flag-don't-reject, the honest-messy-model principle "earning its keep" — exists only if an unknown bound is read as unbounded.

That reading is not neutral. It claims Diane was CTO from the beginning of time until the end of it, which is a much stronger statement than "she was CTO when we spoke." The model chose it by accident, in prose, by writing `valid[?..]` and letting the reader supply the meaning.

**Question**: does an unknown bound mean unbounded, unprovable, or undetermined? It has to be one, and every constraint in the kernel depends on it.

## E3 — `[?..]` conflates "unknown" with "still true"

`a3` is `[?..?]`: started at some unrecorded time, and *as far as we know* still true. `a8` is `[?..Feb]`. But "we do not know when it ended" and "it has not ended" are different facts, and one nullable column cannot hold both.

This lands directly on R1's schema, where `valid_to IS NULL` needs a single meaning. If null means *open*, every unknown end silently becomes a claim of ongoing truth. If null means *unknown*, nothing is ever assertably current.

**Question**: does `valid_to` need to distinguish open from unknown — a second column, or a sentinel?

## E4 — The three-valued reading looks right, and the model already has a precedent

Under `three-valued` the week-3 state is neither *conflict* nor *no conflict* but **undecided**: the world may or may not be contradictory, and we lack the dates to say. That is more honest than either verdict, and it is what §8 claims to want — *"a system that models reality must be able to represent that reality is contradictory"* extends naturally to representing that the contradiction itself is uncertain.

And [F5](02-open-gaps.md) already set the precedent. Unresolved *identity* is represented rather than decided, as `possibly-same-as`, read differently by each consumer. Unresolved *time* deserves the same: a **possible conflict**, rendered as such, never blocking, resolvable by learning one date.

**Question**: adopt three-valued overlap, with "possible conflict" as a first-class state beside `possibly-same-as`?

---

## Answers & agreed conclusions

**(2026-08-23) E3 — An end bound has three states; E2 and E4 fall out of it: AGREED**

Verified by [`prototypes/03-bounds-trace.py`](../prototypes/03-bounds-trace.py), which re-runs the same four weeks with the fix in place. `02-executable-trace.py` is left unchanged as the record of the original finding.

**The asymmetry is the useful part: ends need three states, starts need two.**

| End | Meaning | Phrasing |
|---|---|---|
| known | ended on date X | "she left in February" |
| **OPEN** | has not ended; true now and continuing | "she's their CTO" |
| **UNKNOWN** | may or may not have ended | "she was mentioned as CTO" |

**Representation: `infinity`, not a flag.** Postgres has native `'infinity'` for date and timestamp types — it compares correctly, indexes, and works in range types. So `valid_to = 'infinity'` is open, `valid_to IS NULL` is unknown, and a date is known; `valid_from = '-infinity'` covers the rare "always". No extra column, and no boolean beside a nullable date producing a meaningless fourth combination.

The elegance is that **NULL keeps its actual SQL meaning**, which is *unknown* — so SQL's three-valued logic and the model's uncertainty semantics coincide rather than compete. Recorded as deliberate rather than free: SQL null semantics are a well-known footgun (`NOT IN` with nulls, aggregates skipping nulls, `NOT (x = y)` ≠ `x <> y`), so the overlap predicate gets tested rather than assumed.

**The inference that makes it pay off**: OPEN means *true as of now*, so an open-ended interval provably contains the present moment, and **two open-ended intervals definitely overlap** however unknown their starts are.

**Result — the six-row policy matrix collapsed to one semantics:**

```
infer=False  W3=conflict   W4=undecided  c1=stale  state_at(W2)=ok
infer=True   W3=conflict   W4=none       c1=stale  state_at(W2)=ok
```

**E2 is answered by construction.** Week 3 now fires as a genuine conflict because two open ends share the present, not because an unknown start was silently read as "since the beginning of time." The aggressive reading is gone and the contradiction survives.

**E4 fell out rather than being chosen.** Once UNKNOWN is a distinct state, "undecided" is simply what the comparison returns; three-valued overlap stopped being a policy decision. A **possible conflict** is therefore a first-class state beside `possibly-same-as` (F5), and for the same reason: the model represents uncertainty rather than forcing a verdict.

**E1 is isolated and confirmed.** Week 4 stays *undecided* without the inference — Bob's start is still unknown, so nothing proves the roles apart. The resolution genuinely requires assuming the successor began when the predecessor ended, and that is genuinely an assumption. E1 remains open.

**Deferred deliberately, so it is not rediscovered**: the fourth state, *"ended, date unknown"* — past tense, "she **was** their CTO" — is `end ∈ (start, now)`, a bound that is itself an interval, and the general form of that is a much larger temporal model. In v1 past tense maps to UNKNOWN. The cost is losing conflicts that could have been decided; the error direction is **under**-claiming, which is the reversible side (§2, principle 5).

**Downstream**: R1's schema takes `'infinity'` / NULL / date on both bounds. The extractor gains a judgment — tense to open-versus-unknown — which is fairly robust for present tense and recoverable when wrong, since it is an assertion like any other.

**(2026-08-23) E1 — Boundary inference exists, as a defeasible conclusion; the conflict becomes *explained*, never cleared: AGREED**

Verified by [`prototypes/04-inference-trace.py`](../prototypes/04-inference-trace.py).

**It has to exist.** Without it the undecided conflict never clears, and neither does any other role succession in the user's life. Possible-conflict badges would accumulate permanently, which is §8's notification-fatigue failure in a different costume: a marker that is always on is a marker nobody reads. And the inference is genuinely informative — a functional constraint plus one known boundary really is evidence about the unknown one.

**It is a conclusion, not a derivation — and the reason names a gap §5 had.** §5 discriminated by *who computed it*: "LLM judgments are not logic." That axis fails here, because the rule is fully deterministic and still not a derivation. The right question is **entailed or assumed**. Days-since-last-contact is *implied* by stored data; "Bob started when Diane left" is not, since the same data is equally consistent with a gap, a handover overlap, or a wrong newsletter. So the model needed a category it lacked: **deterministic but defeasible** inference. The existing machinery covers it — a Conclusion already carries `derivedBy`, so this is `derivedBy: constraint-inference` with evidence `[a8, a7, k1]`, the constraint itself being citable.

**The conflict becomes explained, not cleared.** Four states: *none*, *conflict* (provably overlapping), *possible* (undecided), and **explained** (undecided, with an active conclusion accounting for it). The badge does not vanish; it turns from a question into an answer with a citation and a confidence, which keeps it visible (§9's comprehension model) and contestable (§8, where a constraint is a hypothesis about the user's world). Per R3 it auto-records without reaching a prompt, so it costs no interruption budget.

**The finding that came from running it, and it corrected the recommendation.** The first implementation wrote the inferred boundary onto the successor assertion. The result was `W4 after inference: none` — the intervals became provably apart, the conflict vanished outright, and **the assumption became invisible at precisely the moment it started mattering**. Worse, the next inference would have read that assumed date as an observed one.

> **An assumed value never enters the log.** It lives in the conclusion that assumed it, and readers consult that conclusion. Compounding is then structurally impossible rather than guarded against, and retraction has nothing to un-write.

With the fix: `W4 before = possible`, `after = explained`, `after retracting = possible`, and no assumed boundary written anywhere. Defeat the assumption and the question comes back rather than being lost.

**Guardrails, in order:** exactly one candidate may have the unknown bound (two is guessing); the predecessor's end must be observed rather than itself inferred; a third role-holder covering the boundary blocks it, because the succession is then not direct.

---

**All four executable findings answered 2026-08-23.** E2 and E4 fell out of E3 rather than being decided; E1 survived it and then corrected its own recommendation under execution. The pattern from dialogues 01 and 03 held: the answers that stuck were forced, and the one place intuition was trusted — writing an inferred value into the log — is exactly where running it found the mistake.
