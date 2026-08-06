# 0002 — Organize the system by ownership boundary, not by feature

## Status

Accepted — 2026-08-06

## Context

An agent turn is a short loop: assemble context, call a model, maybe run a
tool, record the result. Written directly it is one function of perhaps forty
lines, and for a single-user assistant that would work.

It would also make a specific class of bug invisible. The failures that
characterize agent systems are not algorithmic — the loop is trivial — they are
ownership failures. State written from a place that should only have been
reading. A retry that re-ran a side effect. A tool description that quietly
became permission to run the tool. A failed run that left no record of what it
had already done.

Each of those is easy to introduce in a single function and hard to notice
afterwards, because nothing about the code says which part was supposed to own
what.

## Decision

Split the system into six packages by **who owns what**, not by feature:
`interfaces`, `runtime`, `context`, `model`, `session`, `tools`.

Every package docstring states what the package owns *and what it must not do*.
The "must not" half is the operative one — it is what makes an erosion visible
in review.

Enforce boundaries structurally wherever the language allows it, rather than by
convention. Two examples that carry most of the weight: the model layer imports
no tool module, so it is incapable of executing what it reports; and the session
store returns deep copies, so a caller cannot write by mutating what it read.

The runtime orchestrates and implements nothing. It decides *when* each layer
acts, never *how*.

## Consequences

Ownership questions are answerable by reading one module instead of tracing a
call path. "What goes into context?" is `context/assembly.py`, in full.

The invariants become testable, which is what makes [ADR
0013](0013-test-load-bearing-invariants-only.md) possible at all — a property
with no owner has nowhere to be asserted.

The cost is real: six packages and an explicit protocol for what could have been
one file, and a reader is asked to hold a layer map before anything makes sense.
For a forty-line loop that is a poor trade on its own terms, and it is only
justified by the system being a template meant to be grown and copied.

The runtime is the boundary most likely to erode, because every violation of it
is briefly the easier option — formatting a prompt inline, appending to the
transcript directly. Its package docstring says so explicitly.
