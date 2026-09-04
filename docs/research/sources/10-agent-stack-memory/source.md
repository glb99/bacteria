# Source 10 — The Agent Stack, Part 5: Context, Retrieval, and Memory

- **URL**: https://theagentstack.substack.com/p/the-agent-stack-part-5-context-retrieval
- **Author**: Vinoth Govindarajan · **Published** 2026-04-27
- **Type**: Article, part 5 of an 8-part series on agent infrastructure
- **Ingested**: 2026-08-24, copied verbatim from `bacteria/backend/agent/articles/part-5-context-retrieval-memory.md`, which the agent package fetched on 2026-07-22
- **Raw file**: [`raw.md`](raw.md) — the summary bacteria stored, not the original prose. See *Completeness* below.
- **Status**: complete for our purpose, with one caveat

## Why this is here, and why it is different from sources 01–09

Not cited in `idea.md`. Every earlier source was chosen to build the model; this one was found **after** the model was implemented, inside the target codebase, where it sits in an archive of background reading that informed bacteria's original design.

That makes it the only source we have that was **already in the room** when the thing we are integrating with was designed. Where it agrees with `MENTAL-MODEL.md` the agreement is not coincidence and not influence in the direction we assumed — bacteria read this first, and several of its ADRs are visibly downstream of it.

It earns ingestion because it supplies a **vocabulary for the boundary we kept tripping over**: what is memory, what is retrieval, what is context, and which of those the graph actually is.

## Completeness

`raw.md` is bacteria's own structured summary of the article rather than its full text — thesis, section headings, the failure-mode list, the builder checklist, and direct quotations. Enough to map abstractions against, which is what it is here for. It is **not** enough to quote as if from the original: the pull quotes are verbatim, the connective prose is a summary written by whoever fetched it.

If a decision ever turns on a passage not in the summary, refetch from the URL before relying on it.

## A constraint on how it may be used

bacteria's `backend/agent/CLAUDE.md`:

> `articles/` and `pdfs/` are archived background reading that informed the original design. They are not part of this system's documentation, nothing depends on them, and they should not be cited from code or docs.

So this may inform prisma's thinking and must not be cited from a bacteria ADR or docstring. Where it changes a decision there, the reasoning has to be restated on its own merits.
