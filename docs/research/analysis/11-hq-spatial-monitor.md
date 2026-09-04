# Analysis 11 — HQ, and whether a world is the right surface

Source: [11-hq-spatial-monitor](../sources/11-hq-spatial-monitor/source.md) · brought by the human, 2026-08-26

## What it says

An agency's internal infrastructure monitor. Ten production sites, fourteen repositories, a Stripe account, certificates — the estate you already own — rendered as a colony on Mars you can fly around, each thing a building sized by its own numbers.

The brief is one sentence: **"Nobody reads a dashboard."** Not because the data is missing but because *"a table of green ticks carries no weight. You skim it."* So the table is thrown away and the estate is given a **place**. You do not check on it; you look out of the window.

Seven rules, each stated as a dated log entry:

| | rule |
|---|---|
| Sol 001 | One built volume, one real thing. **"If there's no data behind a building, the building doesn't exist."** Landscape is the only exception and announces itself. |
| Sol 007 | **Colour before text.** A state lands before a word of it is read. Cyan alive, magenta wants attention, white strobe down — and a downed module never dims to nothing, *"because a module that blinks to black disappears at exactly the moment you need it most."* |
| Sol 014 | **A vocabulary of twenty-seven pieces, written down before it was built.** Three are still unplaced and *documented as unplaced*, because the data behind them does not exist. |
| Sol 023 | Unshipped commits are a quarry — work in progress given a location. |
| Sol 031 | The hangar reports on the agents, and when nothing is wired in **it says so**: *"a world that lies once about being busy stops being worth looking at."* |
| Sol 038 | A cargo ship carrying no data at all, whose whole job is to give everything else a size. |
| Sol 046 | A charge lands, the extractor tags it, clicking collects it. A refund *"goes into the ledger, where accounting belongs, and stays out of the sky, where alarms belong."* |

## Relevance to the project

**The convergence is the finding, and it is not about Mars.** Four of HQ's rules are decisions this project already made, arrived at from a different direction:

- *One volume, one real thing* is [§2](../../architecture/memory-graph.md)'s **an assumed value never enters the log**, stated as a rendering discipline instead of a storage one.
- *A vocabulary written down before it was built, with unplaced pieces documented as unplaced* is the **relation catalogue** of [dialogue 07](../dialogues/07-relation-vocabulary.md) — seeded top-down before the data, admitting an entry only when something can back it — together with bacteria's `Not built:` convention, which is the same honesty about absence.
- *A world that lies once stops being worth looking at* is why `run_id` is left null rather than guessed and why `past` and `unknown` both collapse to unknown. Under-claiming is the recoverable direction, in pixels as in rows.
- *Matte rust never states a fact* is a **reserved channel that carries no claim** — structurally the two-surfaces split of [§8](../../architecture/memory-graph.md), where one channel may write and another may not.

That a monitoring toy and an ontology reached the same four rules is evidence the rules are about **representing claims honestly**, not about either domain.

## Connections to other sources

- **[§8](../../architecture/memory-graph.md) / [dialogue 09](../dialogues/09-the-write-routes.md)** — §8 calls the negotiation surface the differentiating layer and notes *no source builds it*. This is the first source that builds an interface with real care, so it is evidence on the one question the project is most short of evidence on. It is also the first source whose subject is the **reading** of a model rather than its structure.
- **[01 — Coyle](01-agentic-ontologies-coyle.md)** — Coyle's ontology is a guardrail the LLM cannot see. HQ is the opposite face: a model rendered so a *person* cannot avoid seeing it. Both assume the model is worth trusting; neither addresses how it gets corrected.
- **[04 — Palantir advanced](04-palantir-advanced-ontology.md)** — Palantir's Scenarios stage a hypothetical and review it before commit. HQ has no such affordance: it is read-only. That gap is the whole of this analysis's conclusion.

## Open questions for the human

1. Is the interest in **seeing** the graph, or in **sharing** it? HQ is single-player — it is *your* estate, and nothing in it supports two people disagreeing about what a building means. The shared mental model this project is after is a two-party artifact, and that is a different design.
2. Would a beautiful read surface make it *easier to postpone* the write surface, which four dialogues now agree is the blocker?
3. Is there any magnitude in a personal graph that could size a mark, given that [dialogue 08's Q1](../dialogues/08-the-schema-is-ahead-of-the-writer.md) settled against keeping repeat counts?

## Provisional conclusions

**The rules transfer. The world does not — not yet, and possibly not ever.**

Three reasons the colony itself does not fit, in descending confidence:

**HQ has almost no edges.** It is a spatial arrangement of *independent items* — a repo, an account, a domain — whose identity is given and whose inventory changes slowly. A personal graph is the reverse: identity is unresolved (`mom`, `Claudia` and `elena` are three nodes for what may be one person), entities arrive constantly, and the content that matters is the **relations**, which HQ has no way to draw. Giving nodes a place says nothing about the part this project is actually about.

**The closed vocabulary is exactly what ADR 0007 refused.** Twenty-seven pieces works because infrastructure is a closed domain. `rel` is an open long tail, and the tail is *where the junk lives* — which is precisely what a person must see in order to curate. A visual vocabulary authored per relation either closes the set, or leaves the most important part of the graph unrenderable.

**Nothing sizes an assertion.** *"At the size its numbers earn"* is the load-bearing trick, and it needs magnitudes. Infrastructure has them; assertions do not, and the one candidate — corroboration count — was deliberately given up.

**What should be taken instead**, and it applies to the console that already exists:

- **State before text.** The console today carries `trust`, `status`, `ends` and `reason` as *columns* — which is the table of green ticks, exactly. Conflict, and the canonical/tail split ADR 0007 made visible, should land as colour before anyone reads a word.
- **Say pending rather than pretending.** The `Not built:` convention is rigorous in the code and absent from the interface.
- **One mark, one record**, with a reserved channel that can never be mistaken for data.
- **The tail should look different, not merely read different.**

And the caution that decides the sequencing: **a prettier read surface does not address the gap, and might disguise it.** [Dialogue 09](../dialogues/09-the-write-routes.md) opened because *you can see it is wrong and cannot say so*. HQ reduces the cost of *noticing* — glance and you know. The cost in an ontology is **judgement**: is this claim true, are these two people one person. Judgement is not glanceable, and making a wrong graph beautiful makes it look authoritative.

Worth revisiting once the write routes are used on real data and [§14](../../architecture/memory-graph.md)'s bet has been settled. Not before.
