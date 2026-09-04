# Dialogue 12 — Nothing ever leaves

> Opened 2026-08-28. [B5](05-what-building-it-taught.md) named retention the largest hole three dialogues ago and nothing has touched it since: *"There is now a route to **see** a personal graph and no route, chore or policy by which anything ever leaves it."*
>
> Opening it because the obvious first feature is the wrong one, and building it would make the hole harder to see rather than smaller.

## What exists

`retract` and `reject`, one claim at a time, through the console. Both are well built — `retract` closes every row saying the same thing, walks the evidence, and marks what was resting on it.

Neither deletes anything. `retract` sets `recorded_until`; the row stays. That is **correct** for an append-only log and it is why "retention" cannot mean what it usually means here.

## The obvious feature is curation, not retention

[B3](05-what-building-it-taught.md) asked for one thing by name: *a bad extractor run is fixed by retracting everything carrying one prompt version.* That is a bulk `retract`, it reuses everything already built, and `session_id` is now recorded so the query has something to filter on.

It is worth having. **It is not retention.** It closes belief in a batch; the rows stay, the log still only grows, and shipping it would let the hole be marked "addressed" while nothing leaves.

## Retention over an append-only log is three different things

**A. Closing belief in bulk.** What B3 asked for. Cheap, safe, reuses `retract`. The log keeps every row.

**B. Actually deleting rows.** What "who can inspect and delete" means outside this codebase, and what an erasure request means legally. It contradicts append-only directly: the whole design rests on *recorded time cannot be backfilled*, and deletion is backfilling by removal. There is no version of this that is only a feature.

**C. Not writing it in the first place.** Undiscussed, and the one I think is the real answer.

## Why C

The pile has a source, and it is not that removal is missing. **Extraction auto-commits.** Every conversation writes claims nobody asked for and nobody reviewed, forever — the design's own failure mode 6, that *assertions are auto-committed, so nothing was ever deliberately chosen to be kept*.

Deleting later is the expensive repair for a cheap prevention. And the ratio is knowable: of everything the extractor has written, a handful has been confirmed and the rest sits inferred, unread, and unremovable except one claim at a time.

The lever is real and already partly built. `origin` separates what the extractor guessed from what a person meant. `_unrepeated` already declines to write a restatement. A run already knows how many claims it dropped and why. What is missing is any rule that says *this one was not worth keeping* before it lands, rather than a route to remove it after.

Concretely, three candidates, none free:

- **A confidence floor.** The extractor already returns a reason per claim and drops malformed ones. It does not weigh anything. A floor means asking the model how sure it is — *asked and cannot be held to*, for the sixth time.
- **A tail that expires.** A claim under an unratified relation that nobody confirms within N days is closed automatically. Cheap and targeted: [07's Q1](07-relation-vocabulary.md) kept the tail *because it is evidence for what the catalogue should become*, and evidence has a shelf life. It also makes the promotion tally self-limiting.
- **Write less per run.** `max_assertions` bounds a run and nothing bounds a conversation. A session that produced forty claims and had two confirmed is not being served by the other thirty-eight.

## Questions

**Q1**: Is B's deletion a thing this design will ever do — and if so, does it need saying now, while there is one owner and nine tables, rather than after the answer is expensive?

**Q2**: Is C the direction, and if so which lever — a confidence floor, an expiring tail, or a bound per conversation?

**Q3**: Ship A anyway? It is a day's work and B3 asked for it. The risk is precisely that it looks like retention.

---

## Answers & agreed conclusions

### Q1 — Deletion will be needed, and append-only never promised otherwise

**Agreed 2026-08-28.** Recorded now rather than built, because the paragraph is cheap today and the argument is expensive once anything depends on rows being permanent.

This graph holds a person's mother, employer and where they live, and [§11](../../architecture/memory-graph.md) already calls a personal graph *"a decades-scale artifact that must outlive the tool that made it"*. Decades plus personal data means an erasure request eventually. *We never decided* is the worst way to meet one.

**The conflict with append-only is narrower than it looks, and the design has been conflating two promises.**

- **Backfilling** is *inserting* a belief the system did not have. [§2](../../architecture/memory-graph.md) forbids it, and rightly: it manufactures a false history, and [Q1 of 07](07-relation-vocabulary.md) turned on exactly this when it refused to move tail rows into the graph with their original timestamps.
- **Deletion** removes a belief the system *did* have. It does not manufacture anything. What it breaks is **replay fidelity** — a past run can no longer be reconstructed against the memory it saw.

Those are different promises. Append-only is a rule about how belief is **revised**: nothing is edited, a correction is a new row, and the old one closes. It was never a guarantee that a row is immortal, and reading it that way is how the design arrived at *nothing ever leaves* without anyone choosing it.

**So erasure is an exceptional operation that knowingly breaks replay**, and saying so costs nothing now. A replayed run after an erasure is incomplete, and that is the correct trade against keeping data somebody asked to have destroyed. What must not happen is erasure disguised as revision — a row removed while the log still reads as though it was never there is the false history §2 actually forbids, so an erasure has to leave a mark saying something was removed, without saying what.

**Not built, deliberately**: the operation itself. There is one owner and no request. What this settles is that the door exists, which is the part that gets built into a corner if left unsaid.

### Q2 — C, and the lever is the expiring tail

**Agreed 2026-08-28.** The pile has a source and it is auto-commit; removal is the expensive repair for a cheap prevention.

**Not a confidence floor.** It rests entirely on an instruction a model can be given and cannot be held to — the sixth instance in this project, after per-claim trust, the naming rule, relative dates, the `value` kind and never mentioning the tool. The answer every previous time was *do not rely on the instruction, make the failure cheap*, and a floor is nothing but reliance.

**Not a bound per conversation.** Arbitrary in the way that reads as principled: the forty-first claim is not worse than the fortieth, and it penalizes exactly the long conversations most worth reading.

**The expiring tail is aimed at the junk and nothing else.** A canonical claim uses agreed vocabulary. A tail claim is *by definition* a word nobody ratified — and [07's Q1](07-relation-vocabulary.md) kept it for a stated reason: it is **evidence for what the catalogue should become**. Evidence has a shelf life. Still unratified and unconfirmed after some window means the evidence has been available and nobody acted on it, which is an answer rather than an absence.

**And it repairs something quietly broken.** The promotion tally counts every tail claim ever written, so a word seen once a year accumulates toward three forever. With expiry, three occurrences means three *recent* ones — a live regularity rather than a lifetime total, which is what the rule of three was always meant to detect. That was not the reason for choosing it and it is the strongest evidence it is right.

**Open inside the answer**: the window. A month is long enough that nobody loses a fact they meant to keep and short enough that junk does not accumulate for a year — but that is a guess, and the honest version measures how long a claim actually takes to be confirmed before choosing a number.

### Q3 — Ship it, and call it what it is

**Agreed.** Bulk retract is worth having, and [B3](05-what-building-it-taught.md) asked for it by name. The only real risk is the word: called *retention* it closes this dialogue while the log still only grows.

It is a **curation tool for undoing a bad run** — one prompt version, one session, one afternoon of a broken extractor. Named that way it is unambiguous, and it does not compete with Q2 because they act on different things: this undoes what a person can point at, and the expiring tail handles what nobody ever will.

Last of the three, because it wants a bad run to undo and there has not been one.
