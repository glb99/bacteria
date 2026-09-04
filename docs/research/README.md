# Research

Where the memory graph's design came from. This tree is **background, not
instruction** — nothing in it is authoritative about the code as it stands. A
conclusion only becomes binding when it graduates into an ADR in
[`../adr/`](../adr/README.md); until then it is somebody thinking out loud.

Imported from the `prisma` research repo, which is now a read-only archive. Its
git history holds the ingestion order; this copy holds the content.

## Do not read this tree by default

It is roughly 800 KB, most of it verbatim source transcripts. Read it when you
need to know *why* a memory-graph decision went the way it did and the ADR does
not say enough. The entry points, in order of usefulness:

1. [`../architecture/memory-graph.md`](../architecture/memory-graph.md) — the
   synthesis. What the model **is**.
2. [`glossary.md`](glossary.md) — the vocabulary. Terms like *valid time*,
   *recorded time*, *canonical core*, *open tail* mean specific things.
3. [`dialogues/`](dialogues/) — human ↔ AI discussions, one per question that
   had to be settled. What the model is, these say **why**.
4. [`analysis/`](analysis/) — one note per source: summary, relevance,
   cross-links, open questions.
5. [`sources/`](sources/) — the raw material, verbatim and unedited. One folder
   per source, `source.md` (URL, type, ingestion date, why it was cited,
   completeness) plus `raw.md`.
6. [`prototypes/`](prototypes/) — executable traces that pin down the temporal
   semantics. `02-executable-trace.py`, `03-bounds-trace.py` and
   `04-inference-trace.py` run standalone and are the fastest way to see
   three-valued overlap and bi-temporal closure behave.

## The founding idea

Represent an agent's memory not as a flat store of facts but as an **ontology**:
an explicit, visualizable model of reality shared between a human and their
agent. Entities and relationships, negotiated rather than silently accumulated,
acting as the substrate a reasoning engine could later stand on.

The differentiating claim is narrow and worth stating precisely: every substrate
concept involved already exists in open source. What did not exist is the
**negotiation surface** — a graph where human and agent jointly propose,
contest, and ratify a model of reality. The substrate is known technology; the
interface is the novel work.

And deliberately **between one human and one agent**. Conflicts are evaluated
within a single owner's graph. Multi-party — a team, a business — needs
cross-owner conflict, provenance per party, a consensus rule and access control,
none of which exist. Deferred with the reasoning in
[`dialogues/10-a-place-to-stand.md`](dialogues/10-a-place-to-stand.md), Q3.

## Adding to it

The rules the research repo ran on, kept because they are what makes the tree
trustworthy:

- **Raw before analysis.** Never analyse a source that has not been ingested
  verbatim. Raw content is the source of truth; keep it unedited.
- **One source, one folder.** `sources/NN-short-slug/` with `source.md` and
  `raw.md`.
- **Analysis format** (`analysis/NN-short-slug.md`): summary → relevance →
  connections to other sources, linked explicitly → open questions → provisional
  conclusions.
- **Dialogue is first-class.** Open questions go to `dialogues/`. Conclusions
  graduate to an ADR only after being discussed or explicitly accepted by a
  human. Record the assumptions the human states — the point is a *shared*
  model.
- **If a source cannot be fully ingested** (no captions, paywall, blocked
  fetch): store what was obtainable, mark `status: incomplete`, continue.
- **Prototypes are throwaway research aids.** Do not grow one into production
  code here; that is what `backend/` is for.
